from datetime import timedelta
from uuid import uuid7

from httpx import AsyncClient
import pytest

from ecommerce.core.security.tokens import issue_token
from tests.modules.catalog import Json, post


@pytest.fixture
def admin(client: AsyncClient) -> None:
    token = issue_token(uuid7(), "access", timedelta(minutes=5), role="admin")
    client.headers["Authorization"] = f"Bearer {token.value}"


@pytest.fixture
async def brand(admin: None, client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/brands", {"name": "Acme"})
    return data


@pytest.fixture
async def category(admin: None, client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/categories", {"name": "Shoes"})
    return data
