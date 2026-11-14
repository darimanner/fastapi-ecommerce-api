import base64
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import patch

from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, TypeAdapter
import pytest

from fastapi_ecommerce_api.core.exceptions.base import ValidationFailedError
from fastapi_ecommerce_api.core.exceptions.handlers import register_exception_handlers
from fastapi_ecommerce_api.core.pagination.cursor import (
    CursorPage,
    CursorParams,
    decode_cursor,
    encode_cursor,
)
from fastapi_ecommerce_api.core.pagination.offset import OffsetParams, Page
from fastapi_ecommerce_api.interfaces.repository import Slice


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str


items_adapter = TypeAdapter(list[ItemOut])

app = FastAPI()
register_exception_handlers(app)


@app.get("/offset")
async def offset_route(params: Annotated[OffsetParams, Query()]) -> OffsetParams:
    return params


@app.get("/cursor")
async def cursor_route(params: Annotated[CursorParams, Query()]) -> list[str | int]:
    return decode_cursor(params.cursor) if params.cursor else []


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_cursor_round_trip() -> None:
    assert decode_cursor(encode_cursor(["abc", 5])) == ["abc", 5]


@pytest.mark.parametrize(
    "token",
    ["!!!", "", b64("{}"), b64("[]"), b64("[1.5]"), b64("[true]"), b64("not json")],
)
def test_decode_rejects_garbage(token: str) -> None:
    with pytest.raises(ValidationFailedError, match="Invalid cursor"):
        decode_cursor(token)


def test_page_from_slice_converts_in_one_call() -> None:
    rows = [SimpleNamespace(name=n) for n in ("a", "b", "c")]

    with patch.object(
        items_adapter, "validate_python", wraps=items_adapter.validate_python
    ) as spy:
        page = Page.from_slice(Slice(rows, has_next=True), items_adapter, total=7)

    spy.assert_called_once()
    assert [i.name for i in page.items] == ["a", "b", "c"]
    assert (page.has_next, page.total) == (True, 7)


def test_cursor_page_sets_next_cursor_only_when_more_rows() -> None:
    rows = [SimpleNamespace(name=n) for n in ("a", "b")]

    more = CursorPage.from_slice(Slice(rows, True), items_adapter, key=lambda r: [r.name])
    last = CursorPage.from_slice(
        Slice(rows, False), items_adapter, key=lambda r: [r.name]
    )

    assert more.next_cursor is not None
    assert decode_cursor(more.next_cursor) == ["b"]
    assert last.next_cursor is None


async def test_query_param_defaults(api: AsyncClient) -> None:
    response = await api.get("/offset")

    assert response.json() == {"limit": 20, "offset": 0}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
async def test_query_params_out_of_bounds_are_422(api: AsyncClient, query: str) -> None:
    response = await api.get(f"/offset?{query}")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


async def test_invalid_cursor_is_problem_422(api: AsyncClient) -> None:
    response = await api.get("/cursor?cursor=!!!")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Invalid cursor"
