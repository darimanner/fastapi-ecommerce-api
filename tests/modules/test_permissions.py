from datetime import timedelta
from uuid import uuid7

from httpx import AsyncClient
import pytest

from ecommerce.core.security.tokens import issue_token

ENDPOINTS = [
    ("/api/v1/admin/brands", "brands"),
    ("/api/v1/admin/categories", "categories"),
    ("/api/v1/admin/products", "products"),
]


def authorize(client: AsyncClient, role: str) -> None:
    token = issue_token(uuid7(), "access", timedelta(minutes=5), role=role)
    client.headers["Authorization"] = f"Bearer {token.value}"


@pytest.mark.parametrize(("url", "resource"), ENDPOINTS)
async def test_no_token_is_401(client: AsyncClient, url: str, resource: str) -> None:
    assert (await client.post(url, json={})).status_code == 401


@pytest.mark.parametrize(("url", "resource"), ENDPOINTS)
async def test_customer_is_403(client: AsyncClient, url: str, resource: str) -> None:
    authorize(client, "customer")
    response = await client.post(url, json={})
    assert response.status_code == 403
    assert response.json()["missing"] == [f"{resource}:write"]


@pytest.mark.parametrize(("url", "resource"), ENDPOINTS)
async def test_admin_passes_the_gate(
    client: AsyncClient, url: str, resource: str
) -> None:
    authorize(client, "admin")
    # An empty body fails validation (422): the permission gate was passed.
    assert (await client.post(url, json={})).status_code == 422


async def test_public_read_needs_no_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/brands")).status_code == 200


async def test_unknown_role_is_401(client: AsyncClient) -> None:
    authorize(client, "root")
    assert (await client.post("/api/v1/admin/brands", json={})).status_code == 401
