from collections.abc import Iterator
import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.core.scratch import Widget, WidgetRepository


@pytest.fixture
def insert_statements(engine: AsyncEngine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(*args: object) -> None:
        statement = str(args[2])
        if statement.lstrip().upper().startswith("INSERT"):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine.sync_engine, "before_cursor_execute", record)


async def add_widgets(widgets: WidgetRepository, count: int) -> list[Widget]:
    return [await widgets.add(Widget(name=f"w{i}")) for i in range(count)]


async def test_uuid7_ids_are_time_ordered(widgets: WidgetRepository) -> None:
    added = await add_widgets(widgets, 3)

    ids = [w.id for w in added]
    assert sorted(ids) == ids
    assert all(i.version == 7 for i in ids)


async def test_get_returns_none_for_missing(widgets: WidgetRepository) -> None:
    assert await widgets.get(uuid.uuid7()) is None


async def test_add_many_inserts_in_one_statement(
    widgets: WidgetRepository, insert_statements: list[str]
) -> None:
    added = await widgets.add_many([{"name": f"bulk{i}"} for i in range(50)])

    assert len(added) == 50
    assert all(isinstance(w, Widget) and w.id for w in added)
    assert len(insert_statements) == 1


async def test_add_many_preserves_input_order(widgets: WidgetRepository) -> None:
    names = [f"ordered{i:04}" for i in range(2500)]

    added = await widgets.add_many([{"name": n} for n in reversed(names)])

    assert [w.name for w in added] == list(reversed(names))


async def test_update_rejects_unknown_field(widgets: WidgetRepository) -> None:
    widget = await widgets.add(Widget(name="w"))

    with pytest.raises(ValueError, match="quantity"):
        await widgets.update(widget, {"quantity": 5})


async def test_add_many_with_no_rows_returns_empty(widgets: WidgetRepository) -> None:
    assert await widgets.add_many([]) == []


async def test_update_and_delete(widgets: WidgetRepository) -> None:
    widget = await widgets.add(Widget(name="w"))

    await widgets.update(widget, {"qty": 5})
    reloaded = await widgets.get(widget.id)
    assert reloaded is not None
    assert reloaded.qty == 5

    await widgets.delete(widget)
    assert await widgets.get(widget.id) is None


async def test_list_offset_has_next(widgets: WidgetRepository) -> None:
    await add_widgets(widgets, 5)

    first = await widgets.list_offset(2, 0)
    last = await widgets.list_offset(2, 4)
    exact = await widgets.list_offset(5, 0)

    assert (len(first.items), first.has_next) == (2, True)
    assert (len(last.items), last.has_next) == (1, False)
    assert (len(exact.items), exact.has_next) == (5, False)


async def test_list_after_walks_all_rows(widgets: WidgetRepository) -> None:
    added = await add_widgets(widgets, 5)
    seen: list[uuid.UUID] = []
    flags: list[bool] = []
    after: uuid.UUID | None = None

    while True:
        page = await widgets.list_after(after, 2)
        seen += [w.id for w in page.items]
        flags.append(page.has_next)
        if not page.has_next:
            break
        after = page.items[-1].id

    assert seen == [w.id for w in added]
    assert flags == [True, True, False]
