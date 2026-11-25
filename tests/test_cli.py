import asyncio
from uuid import uuid7

from httpx import AsyncClient
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from typer.testing import CliRunner, Result

from ecommerce import cli
from ecommerce.core.exceptions.base import ConflictError
from ecommerce.core.security.tokens import decode_token
from ecommerce.modules.auth.models import Role, User
from ecommerce.uow import AppUnitOfWork

EMAIL = "root@example.com"
PASSWORD = "correct horse"  # noqa: S105  test fixture value


async def test_create_admin_can_log_in_as_admin(
    session_factory: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    user = await cli.create_admin(AppUnitOfWork(session_factory), EMAIL, PASSWORD)

    assert user.role == Role.ADMIN
    response = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200
    claims = decode_token(response.json()["access_token"], "access")
    assert claims["role"] == "admin"


async def test_create_admin_duplicate_email_is_a_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await cli.create_admin(AppUnitOfWork(session_factory), EMAIL, PASSWORD)

    with pytest.raises(ConflictError):
        await cli.create_admin(AppUnitOfWork(session_factory), EMAIL, PASSWORD)


def invoke(
    email: str = EMAIL, password: str | None = PASSWORD, prompts: str | None = None
) -> Result:
    # password=None unsets ADMIN_PASSWORD, so the command prompts.
    return CliRunner().invoke(
        cli.app, ["create-admin", email], input=prompts, env={"ADMIN_PASSWORD": password}
    )


# The command runs asyncio.run, a new event loop, so these tests stay sync and fake
# create_admin: the test session_factory is bound to the session-scoped loop.
@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake(uow: object, email: str, password: str) -> None:
        calls.append((email, password))

    monkeypatch.setattr(cli, "create_admin", fake)
    return calls


def test_command_reads_password_from_env(created: list[tuple[str, str]]) -> None:
    result = invoke()

    assert result.exit_code == 0
    assert result.stdout == f"Admin {EMAIL} created\n"
    assert created == [(EMAIL, PASSWORD)]


def test_command_prompts_twice_when_env_is_missing(
    created: list[tuple[str, str]],
) -> None:
    result = invoke(password=None, prompts=f"{PASSWORD}\n{PASSWORD}\n")

    assert result.exit_code == 0
    assert created == [(EMAIL, PASSWORD)]
    assert PASSWORD not in result.output


def test_command_asks_again_when_prompts_differ(
    created: list[tuple[str, str]],
) -> None:
    prompts = f"{PASSWORD}\n{PASSWORD}x\n{PASSWORD}\n{PASSWORD}\n"

    result = invoke(password=None, prompts=prompts)

    assert result.exit_code == 0
    assert "do not match" in result.output
    assert PASSWORD not in result.output
    assert created == [(EMAIL, PASSWORD)]


def test_tracebacks_never_show_locals() -> None:
    # CliRunner bypasses Typer's exception hook, so pin the setting itself.
    assert cli.app.pretty_exceptions_enable is False


def test_command_duplicate_email_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    async def conflict(uow: object, email: str, password: str) -> None:
        raise ConflictError("email already exists")

    monkeypatch.setattr(cli, "create_admin", conflict)

    result = invoke()

    assert result.exit_code == 1
    assert "email already exists" in result.stderr


async def _delete_user(url: str, email: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(delete(User).where(User.email == email))
    finally:
        await engine.dispose()


# The command commits for real on its own engine; the engine fixture only makes
# sure the migrations have run.
@pytest.mark.usefixtures("engine")
def test_command_against_the_database(
    monkeypatch: pytest.MonkeyPatch, postgres_url: str
) -> None:
    email = f"cli-{uuid7().hex}@example.com"
    cli_engine = create_async_engine(postgres_url)
    monkeypatch.setattr(cli, "engine", cli_engine)
    monkeypatch.setattr(
        cli, "session_factory", async_sessionmaker(cli_engine, expire_on_commit=False)
    )
    try:
        assert invoke(email).exit_code == 0
        assert invoke(email).exit_code == 1
    finally:
        asyncio.run(_delete_user(postgres_url, email))


def test_command_short_password_exits_2_without_echoing_it(
    created: list[tuple[str, str]],
) -> None:
    short = "s3cr3t"

    result = invoke(password=short)

    assert result.exit_code == 2
    assert created == []
    assert "password" in result.stderr
    assert short not in result.output
