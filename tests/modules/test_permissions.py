from datetime import timedelta
import re
from uuid import UUID, uuid7

from httpx import AsyncClient
import pytest

from ecommerce.core.security.tokens import issue_token
from ecommerce.main import app
from ecommerce.modules.auth.models import Role
from ecommerce.modules.auth.permissions import ROLE_PERMISSIONS

ENDPOINTS = [
    ("/api/v1/admin/brands", "brands"),
    ("/api/v1/admin/categories", "categories"),
    ("/api/v1/admin/products", "products"),
]

# app.routes holds _IncludedRouter objects on this FastAPI version, not APIRoute,
# so the operations come from the OpenAPI schema.
ADMIN_OPERATIONS = [
    (method.upper(), re.sub(r"\{\w+\}", str(UUID(int=1)), path))
    for path, operations in app.openapi()["paths"].items()
    if path.startswith("/api/v1/admin/")
    for method in operations
]


def authorize(client: AsyncClient, role: str) -> None:
    token = issue_token(uuid7(), "access", timedelta(minutes=5), role=role)
    client.headers["Authorization"] = f"Bearer {token.value}"


def test_admin_sweep_is_not_vacuous() -> None:
    assert ADMIN_OPERATIONS


@pytest.mark.parametrize(("method", "url"), ADMIN_OPERATIONS)
async def test_every_admin_operation_is_gated(
    client: AsyncClient, method: str, url: str
) -> None:
    assert (await client.request(method, url)).status_code == 401

    authorize(client, "customer")
    response = await client.request(method, url)
    assert response.status_code == 403
    assert response.json()["missing"]


def test_every_role_has_permissions() -> None:
    # A role missing here would be a KeyError, i.e. a 500, on its first request.
    assert set(ROLE_PERMISSIONS) == set(Role)


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
