from collections.abc import Mapping
from typing import ClassVar


class AppError(Exception):
    status_code = 500
    title = "Internal Server Error"
    headers: ClassVar[Mapping[str, str]] = {}

    def __init__(self, detail: str | None = None, **extra: object) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


class UnauthorizedError(AppError):
    status_code = 401
    title = "Unauthorized"
    headers: ClassVar[Mapping[str, str]] = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    status_code = 403
    title = "Forbidden"


class NotFoundError(AppError):
    status_code = 404
    title = "Not Found"


class ConflictError(AppError):
    status_code = 409
    title = "Conflict"


class ValidationFailedError(AppError):
    status_code = 422
    title = "Validation Error"


class ServiceUnavailableError(AppError):
    status_code = 503
    title = "Service Unavailable"
