import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce.core.exceptions.base import AppError
from ecommerce.core.exceptions.db import map_integrity_error
from ecommerce.core.exceptions.handlers import register_exception_handlers
from tests.core.scratch import Widget


async def flush_error(session: AsyncSession, *widgets: Widget) -> IntegrityError:
    session.add_all(widgets)
    with pytest.raises(IntegrityError) as caught:
        await session.flush()
    return caught.value


def field_of(error: AppError) -> object:
    errors = error.extra["errors"]
    assert isinstance(errors, list)
    return errors[0]["field"]


async def test_unique_violation_is_409_without_value(db_session: AsyncSession) -> None:
    db_session.add(Widget(name="secret-name"))
    await db_session.flush()

    error = map_integrity_error(await flush_error(db_session, Widget(name="secret-name")))

    assert error.status_code == 409
    assert field_of(error) == "name"
    assert "secret-name" not in f"{error.detail} {error.extra}"


async def test_missing_reference_is_422(db_session: AsyncSession) -> None:
    orphan = Widget(name="orphan", parent_id=uuid.uuid7())

    error = map_integrity_error(await flush_error(db_session, orphan))

    assert error.status_code == 422
    assert field_of(error) == "parent_id"


async def test_still_referenced_is_409(db_session: AsyncSession) -> None:
    parent = Widget(name="parent")
    db_session.add(parent)
    await db_session.flush()
    db_session.add(Widget(name="child", parent_id=parent.id))
    await db_session.flush()

    await db_session.delete(parent)
    with pytest.raises(IntegrityError) as caught:
        await db_session.flush()
    error = map_integrity_error(caught.value)

    assert error.status_code == 409
    assert "widgets" in error.detail


async def test_check_violation_is_422(db_session: AsyncSession) -> None:
    error = map_integrity_error(await flush_error(db_session, Widget(name="w", qty=-1)))

    assert error.status_code == 422
    assert field_of(error) == "qty_non_negative"


async def test_not_null_is_422(db_session: AsyncSession) -> None:
    nameless = Widget(name=None)

    error = map_integrity_error(await flush_error(db_session, nameless))

    assert error.status_code == 422
    assert field_of(error) == "name"


def test_unknown_integrity_error_is_generic_500() -> None:
    error = map_integrity_error(IntegrityError("stmt", {}, Exception("raw driver text")))

    assert error.status_code == 500
    assert error.title == "Internal Server Error"
    assert "raw driver text" not in error.detail


async def test_handler_hides_unknown_integrity_error() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise IntegrityError("stmt", {}, Exception("raw driver text"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        response = await c.get("/boom")

    assert response.status_code == 500
    assert "raw driver text" not in response.text


async def test_handler_returns_problem_json(db_session: AsyncSession) -> None:
    db_session.add(Widget(name="dup"))
    await db_session.flush()
    captured = await flush_error(db_session, Widget(name="dup"))
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise captured

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        response = await c.get("/boom")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["errors"] == [{"field": "name", "message": "already exists"}]
    assert "request_id" in body
