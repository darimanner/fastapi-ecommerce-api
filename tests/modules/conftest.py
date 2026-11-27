from datetime import timedelta
from uuid import UUID, uuid7

from httpx import AsyncClient
import pytest

from ecommerce.core.security.tokens import issue_token
from tests.modules.catalog import Json, post


@pytest.fixture
def admin(client: AsyncClient) -> None:
    token = issue_token(uuid7(), "access", timedelta(minutes=5), role="admin")
    client.headers["Authorization"] = f"Bearer {token.value}"


@pytest.fixture
async def customer(client: AsyncClient) -> UUID:
    body = {"email": f"{uuid7()}@example.com", "password": "correct horse"}
    user_id = UUID((await client.post("/api/v1/auth/register", json=body)).json()["id"])
    token = issue_token(user_id, "access", timedelta(minutes=5), role="customer")
    client.headers["Authorization"] = f"Bearer {token.value}"
    return user_id


@pytest.fixture
async def brand(admin: None, client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/brands", {"name": "Acme"})
    return data


@pytest.fixture
async def category(admin: None, client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/categories", {"name": "Shoes"})
    return data
