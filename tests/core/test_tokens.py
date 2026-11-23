import base64
from datetime import UTC, datetime, timedelta
import json
import uuid

import jwt
from pydantic import SecretStr
import pytest

from ecommerce.config.settings import settings
from ecommerce.core.exceptions.base import UnauthorizedError
from ecommerce.core.security.tokens import decode_token, issue_token

USER_ID = uuid.uuid7()


def b64url(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "sub": str(USER_ID),
        "jti": str(uuid.uuid7()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **overrides,
    }


def assert_rejected(value: str) -> None:
    with pytest.raises(UnauthorizedError, match=r"^Invalid or expired token$"):
        decode_token(value, "access")


def test_issued_token_round_trips() -> None:
    token = issue_token(USER_ID, "access", timedelta(minutes=15), role="admin")

    decoded = decode_token(token.value, "access")

    assert decoded["sub"] == str(USER_ID)
    assert decoded["jti"] == str(token.jti)
    assert decoded["role"] == "admin"
    assert decoded["type"] == "access"
    assert decoded["exp"] - decoded["iat"] == token.expires_in == 900


def test_refresh_token_is_not_an_access_token() -> None:
    token = issue_token(USER_ID, "refresh", timedelta(days=30))

    assert_rejected(token.value)


def test_expired_token_is_rejected() -> None:
    assert_rejected(issue_token(USER_ID, "access", timedelta(seconds=-1)).value)


def test_token_signed_with_another_secret_is_rejected() -> None:
    assert_rejected(jwt.encode(claims(), "another-secret-key-0123456789abcdef"))


def test_unsigned_token_is_rejected() -> None:
    assert_rejected(f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(claims())}.")


@pytest.mark.parametrize("missing", ["jti", "type"])
def test_token_without_required_claim_is_rejected(missing: str) -> None:
    payload = claims()
    del payload[missing]
    secret = settings.auth.secret_key.get_secret_value()

    assert_rejected(jwt.encode(payload, secret, algorithm="HS256"))


def test_secret_is_read_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    token = issue_token(USER_ID, "access", timedelta(minutes=15))
    rotated = settings.auth.model_copy(update={"secret_key": SecretStr("x" * 32)})
    monkeypatch.setattr(settings, "auth", rotated)

    assert_rejected(token.value)
