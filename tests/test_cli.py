import getpass

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce import cli
from ecommerce.core.exceptions.base import ConflictError
from ecommerce.core.security.tokens import decode_token
from ecommerce.modules.auth.models import Role
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


# main() runs asyncio.run, a new event loop, so these tests stay sync and fake
# create_admin: the test session_factory is bound to the session-scoped loop.
@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake(uow: object, email: str, password: str) -> None:
        calls.append((email, password))

    monkeypatch.setattr(cli, "create_admin", fake)
    return calls


def test_main_reads_password_from_env(
    monkeypatch: pytest.MonkeyPatch, created: list[tuple[str, str]]
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)

    assert cli.main(["create-admin", EMAIL]) == 0
    assert created == [(EMAIL, PASSWORD)]


def test_main_prompts_when_env_is_missing(
    monkeypatch: pytest.MonkeyPatch, created: list[tuple[str, str]]
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": PASSWORD)

    assert cli.main(["create-admin", EMAIL]) == 0
    assert created == [(EMAIL, PASSWORD)]


def test_main_duplicate_email_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def conflict(uow: object, email: str, password: str) -> None:
        raise ConflictError("email already exists")

    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setattr(cli, "create_admin", conflict)

    assert cli.main(["create-admin", EMAIL]) == 1
    assert "email already exists" in capsys.readouterr().err


def test_main_short_password_exits_2_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
    created: list[tuple[str, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cr3t")

    assert cli.main(["create-admin", EMAIL]) == 2
    assert created == []
    err = capsys.readouterr().err
    assert "password" in err
    assert "s3cr3t" not in err


def test_main_mismatching_prompts_exit_2(
    monkeypatch: pytest.MonkeyPatch, created: list[tuple[str, str]]
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": next(answers))

    assert cli.main(["create-admin", EMAIL]) == 2
    assert created == []
