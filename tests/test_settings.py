from datetime import timedelta
from pathlib import Path

import pytest

from ecommerce.config.settings import load_settings


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LOGGER__LEVEL", "LOUD"),
        ("DATABASE__URL", "postgresql://u:p@localhost/db"),
        ("CATALOG__MAX_CATEGORY_DEPTH", "0"),
        ("REDIS__URL", "http://localhost:6379"),
        ("AUTH__SECRET_KEY", "x" * 31),
    ],
)
def test_invalid_env_exits_with_variable_name(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit, match=name):
        load_settings()


def test_missing_database_url_exits_with_variable_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATABASE__URL")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit, match="DATABASE__URL: Field required"):
        load_settings()


def test_missing_auth_secret_exits_with_variable_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("AUTH__SECRET_KEY")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit, match="AUTH__SECRET_KEY: Field required"):
        load_settings()


def test_auth_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    auth = load_settings().auth

    assert auth.access_ttl == timedelta(minutes=15)
    assert auth.refresh_ttl == timedelta(days=30)
    assert auth.cookie_secure is True
