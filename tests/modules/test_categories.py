import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any
import uuid

from httpx import AsyncClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fastapi_ecommerce_api.config.settings import settings
from fastapi_ecommerce_api.modules.categories.exceptions import CategoryCycleError
from fastapi_ecommerce_api.modules.categories.models import Category
from fastapi_ecommerce_api.modules.categories.schemas import (
    CategoryCreate,
    CategoryUpdate,
)
from fastapi_ecommerce_api.modules.categories.service import CategoryService
from fastapi_ecommerce_api.uow import AppUnitOfWork

CATEGORIES = "/api/v1/categories"
ADMIN = "/api/v1/admin/categories"


@pytest.fixture
def max_depth_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.catalog, "max_category_depth", 3)


async def create(
    client: AsyncClient, name: str, parent: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = {"name": name, "parent_id": parent and parent["id"]}
    response = await client.post(ADMIN, json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def chain(client: AsyncClient, *names: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for name in names:
        nodes.append(await create(client, name, nodes[-1] if nodes else None))
    return nodes


async def move(client: AsyncClient, node: dict[str, Any], parent: dict[str, Any]) -> Any:
    return await client.patch(f"{ADMIN}/{node['id']}", json={"parent_id": parent["id"]})


async def test_create_child_and_read(client: AsyncClient) -> None:
    root, child = await chain(client, "Shoes", "Running")

    fetched = (await client.get(f"{CATEGORIES}/{child['id']}")).json()
    page = (await client.get(CATEGORIES)).json()

    assert fetched["parent_id"] == root["id"]
    assert fetched["slug"] == "running"
    assert {c["id"] for c in page["items"]} == {root["id"], child["id"]}


async def test_parent_cannot_be_self(client: AsyncClient) -> None:
    node = await create(client, "Shoes")

    response = await move(client, node, node)

    assert response.status_code == 409


async def test_move_under_own_descendant_is_409_with_ids(client: AsyncClient) -> None:
    root, _, grandchild = await chain(client, "a", "b", "c")

    response = await move(client, root, grandchild)

    assert response.status_code == 409
    body = response.json()
    assert (body["category_id"], body["parent_id"]) == (root["id"], grandchild["id"])


@pytest.mark.usefixtures("max_depth_3")
async def test_create_below_max_depth_is_409(client: AsyncClient) -> None:
    *_, leaf = await chain(client, "a", "b", "c")

    response = await client.post(ADMIN, json={"name": "d", "parent_id": leaf["id"]})

    assert response.status_code == 409
    assert response.json()["max_depth"] == 3


@pytest.mark.usefixtures("max_depth_3")
async def test_moving_a_subtree_counts_its_height(client: AsyncClient) -> None:
    subtree_root, _ = await chain(client, "x", "y")
    top, middle = await chain(client, "p", "q")

    too_deep = await move(client, subtree_root, middle)
    fits = await move(client, subtree_root, top)

    assert too_deep.status_code == 409
    assert too_deep.json()["category_id"] == subtree_root["id"]
    assert fits.status_code == 200


@pytest.mark.usefixtures("max_depth_3")
async def test_rename_at_max_depth_is_allowed(client: AsyncClient) -> None:
    *_, parent, leaf = await chain(client, "a", "b", "c")

    renamed = await client.patch(f"{ADMIN}/{leaf['id']}", json={"name": "cc"})
    same_parent = await move(client, leaf, parent)

    assert (renamed.status_code, same_parent.status_code) == (200, 200)


async def test_put_without_parent_moves_to_root(client: AsyncClient) -> None:
    _, child = await chain(client, "Shoes", "Running")

    response = await client.put(f"{ADMIN}/{child['id']}", json={"name": "Trail Running"})

    assert response.status_code == 200
    assert response.json()["parent_id"] is None
    assert response.json()["slug"] == "trail-running"


async def test_unknown_parent_is_422(client: AsyncClient) -> None:
    response = await client.post(
        ADMIN, json={"name": "a", "parent_id": str(uuid.uuid7())}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "parent_id"


async def test_unknown_parent_is_422_even_for_a_too_deep_subtree(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, *_ = await chain(client, "a", "b", "c")
    monkeypatch.setattr(settings.catalog, "max_category_depth", 2)

    response = await client.patch(
        f"{ADMIN}/{root['id']}", json={"parent_id": str(uuid.uuid7())}
    )

    assert response.status_code == 422


async def test_delete_with_children_is_409_and_leaf_is_204(client: AsyncClient) -> None:
    root, child = await chain(client, "Shoes", "Running")

    blocked = await client.delete(f"{ADMIN}/{root['id']}")
    deleted = await client.delete(f"{ADMIN}/{child['id']}")

    assert (blocked.status_code, deleted.status_code) == (409, 204)


class RacingService(CategoryService):
    """Holds its transaction after the guard until the other move has checked too."""

    def __init__(self, uow: AppUnitOfWork, barrier: asyncio.Barrier) -> None:
        super().__init__(uow, max_depth=5)
        self._barrier = barrier

    async def _before_write(
        self, entity: Category | None, values: dict[str, Any]
    ) -> None:
        await super()._before_write(entity, values)
        # With the tree lock the other move blocks inside its guard, so stop waiting.
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            async with asyncio.timeout(0.5):
                await self._barrier.wait()


class StaleReadService(CategoryService):
    """Another admin moves the node right after this request has read it."""

    def __init__(
        self, uow: AppUnitOfWork, concurrent_move: Callable[[], Awaitable[object]]
    ) -> None:
        super().__init__(uow, max_depth=5)
        self._concurrent_move = concurrent_move

    async def _before_write(
        self, entity: Category | None, values: dict[str, Any]
    ) -> None:
        await self._concurrent_move()
        await super()._before_write(entity, values)


@pytest.fixture
async def committed(engine: AsyncEngine) -> AsyncIterator[CommittedTree]:
    # Real commits on separate connections: the savepoint fixtures share one.
    tree = CommittedTree(async_sessionmaker(engine, expire_on_commit=False))
    yield tree
    async with engine.begin() as conn:
        ids = {"ids": tree.ids}
        await conn.execute(
            text("UPDATE categories SET parent_id = NULL WHERE id = ANY(:ids)"), ids
        )
        await conn.execute(text("DELETE FROM categories WHERE id = ANY(:ids)"), ids)


class CommittedTree:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.ids: list[uuid.UUID] = []

    def service(self) -> CategoryService:
        return CategoryService(AppUnitOfWork(self.factory), max_depth=5)

    async def create(self, parent: Category | None = None) -> Category:
        category = await self.service().create(
            CategoryCreate(name=f"c-{uuid.uuid7()}", parent_id=parent and parent.id)
        )
        self.ids.append(category.id)
        return category


async def test_concurrent_cross_moves_cannot_build_a_cycle(
    committed: CommittedTree,
) -> None:
    a, b = await committed.create(), await committed.create()
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        RacingService(AppUnitOfWork(committed.factory), barrier).update(
            a.id, CategoryUpdate(parent_id=b.id)
        ),
        RacingService(AppUnitOfWork(committed.factory), barrier).update(
            b.id, CategoryUpdate(parent_id=a.id)
        ),
        return_exceptions=True,
    )

    assert sorted(type(r).__name__ for r in results) == sorted(
        [Category.__name__, CategoryCycleError.__name__]
    )


async def test_move_is_checked_against_the_committed_parent(
    committed: CommittedTree,
) -> None:
    first, second = await committed.create(), await committed.create()
    node = await committed.create(parent=first)

    def other_admin_moves_node() -> Awaitable[Category]:
        return committed.service().update(node.id, CategoryUpdate(parent_id=second.id))

    service = StaleReadService(AppUnitOfWork(committed.factory), other_admin_moves_node)
    moved = await service.update(node.id, CategoryUpdate(parent_id=first.id))
    stored = await committed.service().get(node.id)

    assert moved.parent_id == stored.parent_id == first.id
