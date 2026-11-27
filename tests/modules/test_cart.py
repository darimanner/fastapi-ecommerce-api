import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

from httpx import AsyncClient
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ecommerce.core.security.tokens import issue_token
from ecommerce.modules.auth.models import User
from ecommerce.modules.cart.models import Cart
from ecommerce.modules.cart.schemas import CartItemAdd
from ecommerce.modules.cart.service import CartService
from ecommerce.modules.categories.models import Category
from ecommerce.modules.products.models import Product, ProductVariant
from ecommerce.uow import AppUnitOfWork
from tests.modules.catalog import ADMIN_PRODUCTS, Json, post, variant

CART = "/api/v1/cart"
ITEMS = f"{CART}/items"
VARIANTS = "/api/v1/admin/variants"


def act_as(client: AsyncClient, user_id: UUID, role: str) -> None:
    token = issue_token(user_id, "access", timedelta(minutes=5), role=role)
    client.headers["Authorization"] = f"Bearer {token.value}"


async def add(client: AsyncClient, variant_id: str, quantity: int = 1) -> Any:
    response = await client.post(
        ITEMS, json={"variant_id": variant_id, "quantity": quantity}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def product(client: AsyncClient, brand: Json, category: Json) -> Json:
    body = {"name": "Trail Runner", "category_id": category["id"]}
    created: Json = await post(client, ADMIN_PRODUCTS, body)
    return created


@pytest.fixture
async def shoe(client: AsyncClient, product: Json) -> Json:
    # Stock 5, price 1000.
    created = await post(
        client,
        f"{ADMIN_PRODUCTS}/{product['id']}/variants",
        [variant("TR-42", size="42")],
    )
    return {**created[0], "product": product}


async def test_empty_cart(client: AsyncClient, customer: UUID) -> None:
    response = await client.get(CART)

    assert response.status_code == 200
    assert response.json() == {"items": [], "subtotal": 0}


async def test_add_accumulates_into_one_line(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])
    cart = await add(client, shoe["id"], 2)

    (line,) = cart["items"]
    assert line == {
        "variant_id": shoe["id"],
        "product_id": shoe["product"]["id"],
        "name": "Trail Runner",
        "sku": "TR-42",
        "options": {"size": "42"},
        "unit_price": 1000,
        "quantity": 3,
        "stock": 5,
        "line_total": 3000,
        "available": True,
    }
    assert cart["subtotal"] == 3000


async def test_patch_sets_quantity(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])

    response = await client.patch(f"{ITEMS}/{shoe['id']}", json={"quantity": 5})

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 5


async def test_delete_line_and_clear(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])

    assert (await client.delete(f"{ITEMS}/{shoe['id']}")).status_code == 204
    assert (await client.get(CART)).json()["items"] == []

    await add(client, shoe["id"])
    assert (await client.delete(CART)).status_code == 204
    assert (await client.get(CART)).json()["items"] == []


async def test_delete_without_a_cart_is_a_no_op(
    client: AsyncClient, customer: UUID
) -> None:
    assert (await client.delete(f"{ITEMS}/{uuid7()}")).status_code == 204
    assert (await client.delete(CART)).status_code == 204


async def test_delete_absent_line_is_204(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])

    assert (await client.delete(f"{ITEMS}/{uuid7()}")).status_code == 204
    assert len((await client.get(CART)).json()["items"]) == 1


async def test_add_over_stock_is_409_and_keeps_the_line(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"], 4)

    response = await client.post(ITEMS, json={"variant_id": shoe["id"], "quantity": 2})

    assert response.status_code == 409
    assert response.json()["stock"] == 5
    assert (await client.get(CART)).json()["items"][0]["quantity"] == 4


async def test_patch_over_stock_is_409(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])

    response = await client.patch(f"{ITEMS}/{shoe['id']}", json={"quantity": 6})

    assert response.status_code == 409
    assert response.json()["stock"] == 5
    assert (await client.get(CART)).json()["items"][0]["quantity"] == 1


async def test_patch_missing_line_is_404(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    response = await client.patch(f"{ITEMS}/{shoe['id']}", json={"quantity": 1})

    assert response.status_code == 404


async def test_add_unknown_variant_is_404(client: AsyncClient, customer: UUID) -> None:
    response = await client.post(ITEMS, json={"variant_id": str(uuid7())})

    assert response.status_code == 404


async def test_add_inactive_product_is_404(
    client: AsyncClient, product: Json, shoe: Json, customer: UUID
) -> None:
    admin = UUID(int=0)
    act_as(client, admin, "admin")
    await client.patch(
        f"/api/v1/admin/products/{product['id']}", json={"is_active": False}
    )
    act_as(client, customer, "customer")

    response = await client.post(ITEMS, json={"variant_id": shoe["id"]})

    assert response.status_code == 404


@pytest.mark.parametrize("quantity", [0, -1, 1001])
async def test_quantity_out_of_range_is_422(
    client: AsyncClient, shoe: Json, customer: UUID, quantity: int
) -> None:
    body = {"variant_id": shoe["id"], "quantity": quantity}

    assert (await client.post(ITEMS, json=body)).status_code == 422
    assert (await client.patch(f"{ITEMS}/{shoe['id']}", json=body)).status_code == 422


async def test_line_becomes_unavailable(
    client: AsyncClient, product: Json, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"], 3)
    act_as(client, UUID(int=0), "admin")

    await client.patch(f"{VARIANTS}/{shoe['id']}", json={"stock": 2})
    act_as(client, customer, "customer")
    low_stock = (await client.get(CART)).json()["items"][0]

    act_as(client, UUID(int=0), "admin")
    await client.patch(f"{VARIANTS}/{shoe['id']}", json={"stock": 5})
    await client.patch(
        f"/api/v1/admin/products/{product['id']}", json={"is_active": False}
    )
    act_as(client, customer, "customer")
    deactivated = (await client.get(CART)).json()["items"][0]

    assert low_stock["available"] is False
    assert deactivated["available"] is False
    assert "is_active" not in deactivated


async def test_deleting_a_variant_drops_its_line(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])
    act_as(client, UUID(int=0), "admin")
    assert (await client.delete(f"{VARIANTS}/{shoe['id']}")).status_code == 204
    act_as(client, customer, "customer")

    response = await client.get(CART)

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_users_do_not_see_each_other(
    client: AsyncClient, shoe: Json, customer: UUID
) -> None:
    await add(client, shoe["id"])
    body = {"email": f"{uuid7()}@example.com", "password": "correct horse"}
    other = UUID((await client.post("/api/v1/auth/register", json=body)).json()["id"])
    act_as(client, other, "customer")

    assert (await client.get(CART)).json()["items"] == []
    await add(client, shoe["id"], 2)
    assert (await client.delete(f"{ITEMS}/{shoe['id']}")).status_code == 204
    await add(client, shoe["id"], 2)
    assert (await client.delete(CART)).status_code == 204
    assert (await client.get(CART)).json()["items"] == []

    act_as(client, customer, "customer")
    assert (await client.get(CART)).json()["items"][0]["quantity"] == 1


async def test_token_of_a_deleted_user_is_422(client: AsyncClient, shoe: Json) -> None:
    act_as(client, uuid7(), "customer")

    response = await client.post(ITEMS, json={"variant_id": shoe["id"]})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_no_token_is_401(client: AsyncClient) -> None:
    assert (await client.get(CART)).status_code == 401


class Committed:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.user_id = uuid7()
        self.product_id = uuid7()
        self.category_id = uuid7()
        self.variant_id = uuid7()


@pytest.fixture
async def committed(engine: AsyncEngine) -> AsyncIterator[Committed]:
    # Real commits on separate connections: the savepoint fixtures share one.
    data = Committed(async_sessionmaker(engine, expire_on_commit=False))
    async with data.factory.begin() as session:
        session.add_all(
            [
                User(
                    id=data.user_id,
                    email=f"{data.user_id}@example.com",
                    password_hash="x",  # noqa: S106  test fixture value
                ),
                Category(id=data.category_id, name="c", slug=f"c-{data.category_id}"),
            ]
        )
        await session.flush()
        session.add(
            Product(
                id=data.product_id,
                name="p",
                slug=f"p-{data.product_id}",
                category_id=data.category_id,
            )
        )
        await session.flush()
        session.add(
            ProductVariant(
                id=data.variant_id,
                product_id=data.product_id,
                sku=f"sku-{data.variant_id}",
                price=100,
                stock=10,
                options={},
            )
        )
    yield data
    async with data.factory.begin() as session:
        await session.execute(delete(User).where(User.id == data.user_id))
        await session.execute(delete(Product).where(Product.id == data.product_id))
        await session.execute(delete(Category).where(Category.id == data.category_id))


async def test_concurrent_first_adds_make_one_cart(committed: Committed) -> None:
    payload = CartItemAdd(variant_id=committed.variant_id, quantity=2)

    def service() -> CartService:
        return CartService(AppUnitOfWork(committed.factory))

    await asyncio.gather(
        service().add(committed.user_id, payload),
        service().add(committed.user_id, payload),
    )

    async with committed.factory() as session:
        carts = await session.scalar(
            select(func.count())
            .select_from(Cart)
            .where(Cart.user_id == committed.user_id)
        )
    cart = await service().get(committed.user_id)
    assert carts == 1
    assert [line.quantity for line in cart.items] == [4]
