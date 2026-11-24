import asyncio
from datetime import timedelta
from typing import Any
import uuid

from httpx import AsyncClient, Response
import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce.core.security.passwords import DUMMY_HASH, verify_password
from ecommerce.core.security.tokens import decode_token, issue_token
from ecommerce.modules.auth import service
from ecommerce.modules.auth.models import Role, User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/users/me"
EMAIL = "ann@example.com"
PASSWORD = "correct horse"  # noqa: S105  test fixture value
COOKIE_ATTRIBUTES = ("HttpOnly", "Secure", "SameSite=strict", "Path=/api/v1/auth")


async def register(client: AsyncClient, email: str, password: str = PASSWORD) -> Any:
    return await client.post(REGISTER, json={"email": email, "password": password})


async def login(
    client: AsyncClient, email: str = EMAIL, password: str = PASSWORD
) -> Response:
    return await client.post(LOGIN, json={"email": email, "password": password})


async def refresh(client: AsyncClient, cookie: str) -> Response:
    # An explicit Cookie header wins over the client jar, so old cookies can be replayed.
    return await client.post(REFRESH, headers={"Cookie": f"refresh_token={cookie}"})


async def update_user(db_session: AsyncSession, **values: object) -> None:
    await db_session.execute(update(User).where(User.email == EMAIL).values(**values))
    await db_session.commit()


@pytest.fixture
async def signed_in(client: AsyncClient) -> Response:
    await register(client, EMAIL)
    response = await login(client)
    assert response.status_code == 200, response.text
    return response


async def test_register_ignores_a_requested_role(client: AsyncClient) -> None:
    response = await client.post(
        REGISTER, json={"email": EMAIL, "password": PASSWORD, "role": "admin"}
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "customer"


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


@pytest.mark.parametrize("email", [EMAIL, "ANN@EXAMPLE.COM"])
async def test_login_returns_access_token_and_refresh_cookie(
    client: AsyncClient, redis: Redis, email: str
) -> None:
    user_id = (await register(client, EMAIL)).json()["id"]

    response = await login(client, email)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"  # noqa: S105  OAuth token type, not a secret
    assert body["expires_in"] == 900
    assert decode_token(body["access_token"], "access")["role"] == "customer"
    cookie = response.headers["set-cookie"]
    for attribute in (*COOKIE_ATTRIBUTES, "Max-Age=2592000"):
        assert attribute in cookie
    # Only the refresh token is stored, keyed by its jti, never the access token.
    jti = decode_token(response.cookies["refresh_token"], "refresh")["jti"]
    key = f"auth:refresh:{jti}"
    assert await redis.keys() == [key.encode()]
    assert await redis.get(key) == user_id.encode()
    assert 0 < await redis.ttl(key) <= 2592000


async def test_wrong_password_and_unknown_email_look_the_same(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client, EMAIL)
    calls: list[str] = []

    async def counting(plain: str, hashed: str) -> bool:
        calls.append(hashed)
        return await verify_password(plain, hashed)

    monkeypatch.setattr(service, "verify_password", counting)

    unknown = await login(client, "bob@example.com")
    assert calls == [DUMMY_HASH]
    wrong = await login(client, password=PASSWORD + "!")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


async def test_inactive_user_cannot_log_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client, EMAIL)
    await update_user(db_session, is_active=False)

    response = await login(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_refresh_rotates_the_token(
    client: AsyncClient, signed_in: Response
) -> None:
    old = signed_in.cookies["refresh_token"]

    response = await client.post(REFRESH)  # the cookie comes from the client jar

    assert response.status_code == 200, response.text
    assert response.json()["access_token"] != signed_in.json()["access_token"]
    assert response.cookies["refresh_token"] != old
    assert (await refresh(client, old)).status_code == 401


async def test_concurrent_refreshes_let_only_one_through(
    client: AsyncClient, signed_in: Response
) -> None:
    cookie = signed_in.cookies["refresh_token"]

    responses = await asyncio.gather(refresh(client, cookie), refresh(client, cookie))

    assert {r.status_code for r in responses} == {200, 401}


async def test_refresh_fails_after_deactivation(
    client: AsyncClient, signed_in: Response, db_session: AsyncSession
) -> None:
    await update_user(db_session, is_active=False)

    response = await client.post(REFRESH)

    assert response.status_code == 401


async def test_refresh_issues_the_current_role(
    client: AsyncClient, signed_in: Response, db_session: AsyncSession
) -> None:
    await update_user(db_session, role=Role.ADMIN)

    response = await client.post(REFRESH)

    assert decode_token(response.json()["access_token"], "access")["role"] == "admin"


async def test_access_token_is_not_a_refresh_token(
    client: AsyncClient, signed_in: Response
) -> None:
    response = await refresh(client, signed_in.json()["access_token"])

    assert response.status_code == 401


async def test_refresh_without_cookie_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post(REFRESH)

    assert response.status_code == 401


async def test_logout_clears_the_cookie_and_revokes_the_token(
    client: AsyncClient, signed_in: Response
) -> None:
    old = signed_in.cookies["refresh_token"]

    response = await client.post(LOGOUT)

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    for attribute in (*COOKIE_ATTRIBUTES, "Max-Age=0"):
        assert attribute in cookie
    assert "refresh_token" not in client.cookies
    assert (await refresh(client, old)).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Cookie": "refresh_token=garbage"}])
async def test_logout_without_a_valid_cookie_succeeds(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post(LOGOUT, headers=headers)

    assert response.status_code == 204


@pytest.mark.parametrize("command", ["set", "getdel"])
async def test_token_endpoints_fail_closed_when_redis_is_down(
    client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    await register(client, EMAIL)
    signed = await login(client)
    cookie = signed.cookies["refresh_token"]

    async def down(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError

    monkeypatch.setattr(redis, command, down)

    response = await login(client) if command == "set" else await refresh(client, cookie)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("endpoint", ["login", "refresh"])
async def test_token_responses_are_not_cacheable(
    client: AsyncClient, endpoint: str
) -> None:
    await register(client, EMAIL)
    signed = await login(client)
    response = (
        signed
        if endpoint == "login"
        else await refresh(client, signed.cookies["refresh_token"])
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_me_returns_the_current_user(
    client: AsyncClient, signed_in: Response
) -> None:
    response = await client.get(ME, headers=bearer(signed_in.json()["access_token"]))

    assert response.status_code == 200, response.text
    assert response.json()["email"] == EMAIL


async def test_me_without_a_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(ME)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_rejects_a_refresh_token(
    client: AsyncClient, signed_in: Response
) -> None:
    response = await client.get(ME, headers=bearer(client.cookies["refresh_token"]))

    assert response.status_code == 401


async def test_me_for_a_deleted_user_is_unauthorized(client: AsyncClient) -> None:
    token = issue_token(uuid.uuid7(), "access", timedelta(minutes=5), role="customer")

    response = await client.get(ME, headers=bearer(token.value))

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("ttl", "claims"),
    [
        (timedelta(seconds=-1), {"role": "customer"}),
        (timedelta(minutes=5), {"role": "root"}),
        (timedelta(minutes=5), {}),
    ],
    ids=["expired", "unknown-role", "missing-role"],
)
async def test_me_rejects_bad_access_tokens(
    client: AsyncClient, signed_in: Response, ttl: timedelta, claims: dict[str, str]
) -> None:
    sub = decode_token(signed_in.json()["access_token"], "access")["sub"]
    token = issue_token(uuid.UUID(sub), "access", ttl, **claims)

    response = await client.get(ME, headers=bearer(token.value))

    assert response.status_code == 401
