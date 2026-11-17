from httpx import AsyncClient
import pytest

from tests.modules.catalog import Json, post


@pytest.fixture
async def brand(client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/brands", {"name": "Acme"})
    return data


@pytest.fixture
async def category(client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/categories", {"name": "Shoes"})
    return data
