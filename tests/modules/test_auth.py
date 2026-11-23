from typing import Any

from httpx import AsyncClient
import pytest

REGISTER = "/api/v1/auth/register"
PASSWORD = "correct horse"  # noqa: S105  test fixture value


async def register(client: AsyncClient, email: str, password: str = PASSWORD) -> Any:
    return await client.post(REGISTER, json={"email": email, "password": password})


async def test_register_returns_customer_without_secrets(client: AsyncClient) -> None:
    response = await register(client, "ann@example.com")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "customer"
    assert body["is_active"] is True
    assert body["id"]
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_lowercases_email(client: AsyncClient) -> None:
    response = await register(client, "Ann@Example.com")

    assert response.json()["email"] == "ann@example.com"


async def test_duplicate_email_conflicts_case_insensitively(client: AsyncClient) -> None:
    await register(client, "ann@example.com")

    response = await register(client, "Ann@Example.com")

    assert response.status_code == 409
    assert response.json()["errors"][0]["field"] == "email"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("ann@example.com", "x" * 7),
        ("ann@example.com", "x" * 129),
        ("not-an-email", PASSWORD),
    ],
)
async def test_register_rejects_invalid_input(
    client: AsyncClient, email: str, password: str
) -> None:
    response = await register(client, email, password)

    assert response.status_code == 422
