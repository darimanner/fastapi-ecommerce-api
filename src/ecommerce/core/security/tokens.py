from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7

import jwt

from ecommerce.config.settings import settings
from ecommerce.core.exceptions.base import UnauthorizedError

type TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class Token:
    value: str
    jti: UUID
    expires_in: int  # seconds


def issue_token(
    subject: UUID, token_type: TokenType, ttl: timedelta, **claims: str
) -> Token:
    jti = uuid7()
    now = datetime.now(UTC)
    # Extra claims go first so they can never override the reserved ones.
    payload = {
        **claims,
        "sub": str(subject),
        "jti": str(jti),
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    value = jwt.encode(
        payload, settings.auth.secret_key.get_secret_value(), algorithm="HS256"
    )
    return Token(value=value, jti=jti, expires_in=int(ttl.total_seconds()))


def decode_token(value: str, token_type: TokenType) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            value,
            settings.auth.secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "jti", "type"]},
        )
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid or expired token") from None
    if claims["type"] != token_type:
        raise UnauthorizedError("Invalid or expired token")
    return claims
