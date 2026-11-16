import base64
from collections.abc import Callable
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter

from ecommerce.core.exceptions.base import ValidationFailedError
from ecommerce.interfaces.repository import Slice

type CursorKey = list[str | int]

MAX_CURSOR_LENGTH = 512


class CursorParams(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    cursor: str | None = None


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None

    @classmethod
    def from_slice(
        cls,
        slice_: Slice[Any],
        adapter: TypeAdapter[list[T]],
        key: Callable[[Any], CursorKey],
    ) -> CursorPage[T]:
        items = adapter.validate_python(slice_.items, from_attributes=True)
        next_cursor = encode_cursor(key(slice_.items[-1])) if slice_.has_next else None
        return cls.model_construct(items=items, next_cursor=next_cursor)


def encode_cursor(values: CursorKey) -> str:
    raw = json.dumps(values, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(token: str) -> CursorKey:
    """Decode a client-supplied cursor; anything malformed is a 422, never a 500."""
    # Real cursors are short; the cap also stops deep-nesting JSON (RecursionError).
    if len(token) > MAX_CURSOR_LENGTH:
        raise ValidationFailedError("Invalid cursor")
    try:
        values = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    except ValueError:  # binascii, unicode and JSON errors all subclass it
        raise ValidationFailedError("Invalid cursor") from None
    if not (isinstance(values, list) and values and all(map(_is_key_part, values))):
        raise ValidationFailedError("Invalid cursor")
    return values


def decode_id_cursor(token: str) -> UUID:
    """Decode a cursor holding a single entity id, as produced for `list_after`."""
    values = decode_cursor(token)
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValidationFailedError("Invalid cursor")
    try:
        return UUID(values[0])
    except ValueError:
        raise ValidationFailedError("Invalid cursor") from None


def _is_key_part(value: object) -> bool:
    return isinstance(value, str | int) and not isinstance(value, bool)
