import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from tests.core.scratch import Widget, WidgetRepository


class WidgetUoW(SQLAlchemyUnitOfWork):
    widgets: WidgetRepository

    def _init_repositories(self) -> None:
        self.widgets = WidgetRepository(self.session)


async def stored(factory: async_sessionmaker[AsyncSession], name: str) -> Widget | None:
    async with factory() as session:
        return await session.scalar(select(Widget).where(Widget.name == name))


async def test_commit_persists(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with WidgetUoW(session_factory) as uow:
        await uow.widgets.add(Widget(name="kept"))
        await uow.commit()

    assert await stored(session_factory, "kept") is not None


async def test_entities_stay_readable_after_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with WidgetUoW(session_factory) as uow:
        widget = await uow.widgets.add(Widget(name="readable"))
        await uow.commit()

        assert widget.name == "readable"


async def test_exit_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with WidgetUoW(session_factory) as uow:
        await uow.widgets.add(Widget(name="dropped"))

    assert await stored(session_factory, "dropped") is None


async def test_exception_rolls_back_and_propagates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with WidgetUoW(session_factory) as uow:
            await uow.widgets.add(Widget(name="failed"))
            raise RuntimeError("boom")

    assert await stored(session_factory, "failed") is None


async def test_rollback_discards_pending_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with WidgetUoW(session_factory) as uow:
        await uow.widgets.add(Widget(name="undone"))
        await uow.rollback()
        await uow.commit()

    assert await stored(session_factory, "undone") is None


async def test_session_closed_after_exit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with WidgetUoW(session_factory) as uow:
        await uow.widgets.add(Widget(name="open"))

    assert not uow.session.in_transaction()
