from collections.abc import Callable
import re
from typing import Any

from sqlalchemy.exc import IntegrityError

from ecommerce.core.exceptions.base import (
    AppError,
    ConflictError,
    ValidationFailedError,
)

KEY_COLUMNS = re.compile(r"Key \((.+?)\)=")


def map_integrity_error(exc: IntegrityError) -> AppError:
    """Turn a constraint violation into a client error, or a generic 500 if unknown."""
    # The asyncpg error with sqlstate and constraint details sits behind the DBAPI one.
    cause: Any = getattr(exc.orig, "__cause__", None)
    mapper = MAPPERS.get(getattr(cause, "sqlstate", None) or "")
    return mapper(cause) if mapper else AppError()


def _unique(cause: Any) -> AppError:
    field = _key_field(cause)
    return ConflictError(
        f"{field} already exists", errors=_errors(field, "already exists")
    )


def _foreign_key(cause: Any) -> AppError:
    if "is still referenced" in (cause.detail or ""):
        return ConflictError(f"Resource is still referenced by {cause.table_name}")
    field = _key_field(cause)
    return ValidationFailedError(
        f"Referenced {field} does not exist", errors=_errors(field, "does not exist")
    )


def _check(cause: Any) -> AppError:
    name = cause.constraint_name.removeprefix(f"ck_{cause.table_name}_")
    return ValidationFailedError(
        f"Constraint {name} failed", errors=_errors(name, "check failed")
    )


def _not_null(cause: Any) -> AppError:
    column = cause.column_name
    return ValidationFailedError(
        f"{column} is required", errors=_errors(column, "is required")
    )


def _key_field(cause: Any) -> str:
    match = KEY_COLUMNS.search(cause.detail or "")
    return match.group(1) if match else "value"


def _errors(field: str, message: str) -> list[dict[str, str]]:
    return [{"field": field, "message": message}]


MAPPERS: dict[str, Callable[[Any], AppError]] = {
    "23505": _unique,
    "23503": _foreign_key,
    "23514": _check,
    "23502": _not_null,
}
