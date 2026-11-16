from typing import Any
import uuid

from pydantic import BaseModel
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce.core.crud import CRUDService
from ecommerce.core.exceptions.base import NotFoundError
from ecommerce.core.pagination.offset import OffsetParams
from ecommerce.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from tests.core.scratch import Widget, WidgetRepository


class WidgetCreate(BaseModel):
    name: str
    qty: int = 0


class WidgetUpdate(BaseModel):
    name: str | None = None
    qty: int | None = None


class WidgetUoW(SQLAlchemyUnitOfWork):
    widgets: WidgetRepository

    def _init_repositories(self) -> None:
        self.widgets = WidgetRepository(self.session)


type WidgetService = CRUDService[Widget, WidgetCreate, WidgetUpdate]


class RecordingService(CRUDService[Widget, WidgetCreate, WidgetUpdate]):
    def __init__(self, uow: WidgetUoW, fail: bool = False) -> None:
        super().__init__(uow, lambda: uow.widgets)
        self.calls: list[tuple[Widget | None, dict[str, Any]]] = []
        self.after_writes = 0
        self.fail = fail

    async def _before_write(self, entity: Widget | None, values: dict[str, Any]) -> None:
        self.calls.append((entity, values))
        if self.fail:
            raise RuntimeError("rejected")

    async def _after_write(self) -> None:
        self.after_writes += 1


@pytest.fixture
def service(session_factory: async_sessionmaker[AsyncSession]) -> WidgetService:
    uow = WidgetUoW(session_factory)
    return CRUDService(uow, lambda: uow.widgets)


async def test_create_then_get(service: WidgetService) -> None:
    created = await service.create(WidgetCreate(name="w", qty=3))

    fetched = await service.get(created.id)

    assert (fetched.name, fetched.qty) == ("w", 3)


async def test_get_missing_is_not_found(service: WidgetService) -> None:
    missing = uuid.uuid7()

    with pytest.raises(NotFoundError, match=f"Widget {missing} not found"):
        await service.get(missing)


async def test_update_changes_only_sent_fields(service: WidgetService) -> None:
    created = await service.create(WidgetCreate(name="w", qty=3))

    updated = await service.update(created.id, WidgetUpdate(name="renamed"))

    assert (updated.name, updated.qty) == ("renamed", 3)


async def test_replace_resets_omitted_fields(service: WidgetService) -> None:
    created = await service.create(WidgetCreate(name="w", qty=3))

    replaced = await service.replace(created.id, WidgetCreate(name="new"))

    assert (replaced.name, replaced.qty) == ("new", 0)


async def test_delete_removes(service: WidgetService) -> None:
    created = await service.create(WidgetCreate(name="w"))

    await service.delete(created.id)

    with pytest.raises(NotFoundError):
        await service.get(created.id)


async def test_delete_missing_is_not_found(service: WidgetService) -> None:
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid7())


async def test_list_offset_reports_has_next(service: WidgetService) -> None:
    for i in range(3):
        await service.create(WidgetCreate(name=f"w{i}"))

    page = await service.list_offset(OffsetParams(limit=2))

    assert (len(page.items), page.has_next) == (2, True)


async def test_hook_sees_create_and_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = RecordingService(WidgetUoW(session_factory))

    created = await service.create(WidgetCreate(name="w"))
    await service.update(created.id, WidgetUpdate(qty=5))

    assert service.calls[0] == (None, {"name": "w", "qty": 0})
    assert service.calls[1][0] is not None
    assert service.calls[1][0].id == created.id
    assert service.calls[1][1] == {"qty": 5}


async def test_hook_failure_persists_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = WidgetUoW(session_factory)
    failing = RecordingService(uow, fail=True)

    with pytest.raises(RuntimeError, match="rejected"):
        await failing.create(WidgetCreate(name="w"))

    page = await CRUDService[Widget, WidgetCreate, WidgetUpdate](
        uow, lambda: uow.widgets
    ).list_offset(OffsetParams())
    assert page.items == []
    assert failing.after_writes == 0


async def test_after_write_runs_once_per_committed_write(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = RecordingService(WidgetUoW(session_factory))

    created = await service.create(WidgetCreate(name="w"))
    await service.update(created.id, WidgetUpdate(qty=5))
    await service.replace(created.id, WidgetCreate(name="r"))
    await service.delete(created.id)
    with pytest.raises(NotFoundError):
        await service.delete(created.id)

    assert service.after_writes == 4
