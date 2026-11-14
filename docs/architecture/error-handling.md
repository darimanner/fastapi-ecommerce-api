# Error Handling

> Status: partially implemented

Implemented today: `AppError`, `NotFoundError`, `ConflictError`, `ValidationFailedError` and `ServiceUnavailableError` in `core/exceptions/base.py`, and RFC 7807 `application/problem+json` handlers in `core/exceptions/handlers.py` (with `request_id` and `errors[]` for validation failures). The rest of this document is the target design.

## Principles

- Services raise **domain** exceptions, not `HTTPException`
- One global handler translates them to HTTP using the **RFC 7807 Problem Details** format
- No "magic" `Exception("smth went wrong")`
- 5xx errors are logged with a traceback; 4xx errors are only a warning, with no alert

## Hierarchy

```python
# src/fastapi_ecommerce_api/core/exceptions/base.py
class AppError(Exception):
    """Root of all domain exceptions."""

    status_code: int = 500
    error_type: str = "internal-error"
    title: str = "Internal Server Error"


class NotFoundError(AppError):
    status_code = 404
    error_type = "not-found"
    title = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    error_type = "conflict"
    title = "Conflict"


class ValidationFailedError(AppError):
    status_code = 422
    error_type = "validation-error"
    title = "Validation failed"


class UnauthorizedError(AppError):
    status_code = 401
    error_type = "unauthorized"
    title = "Authentication required"


class ForbiddenError(AppError):
    status_code = 403
    error_type = "forbidden"
    title = "Forbidden"


class RateLimitedError(AppError):
    status_code = 429
    error_type = "rate-limited"
    title = "Too many requests"
```

Concrete modules inherit from these:

```python
# src/fastapi_ecommerce_api/modules/brands/exceptions.py
class BrandNotFoundError(NotFoundError):
    title = "Brand not found"

    def __init__(self, brand_id: int) -> None:
        super().__init__(f"Brand {brand_id} does not exist")
        self.brand_id = brand_id


class BrandAlreadyExistsError(ConflictError):
    title = "Brand already exists"

    def __init__(self, name: str) -> None:
        super().__init__(f"Brand with name '{name}' already exists")
        self.name = name
```

## RFC 7807 Problem Details

All HTTP errors share a single format with the media type `application/problem+json`:

```json
{
  "type": "https://api.example.com/errors/not-found",
  "title": "Brand not found",
  "status": 404,
  "detail": "Brand 42 does not exist",
  "instance": "/api/v1/brands/42",
  "request_id": "5f8b1e..."
}
```

`request_id` is taken from the `structlog` context, which lets you link an error seen by the client to the server logs.

For `ValidationFailedError` an `errors[]` field is added:

```json
{
  "type": "...",
  "title": "Validation failed",
  "status": 422,
  "errors": [
    {"field": "name", "message": "String should have at least 1 character"}
  ]
}
```

## Handler

```python
# src/fastapi_ecommerce_api/core/exceptions/handlers.py
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    log_method = log.warning if exc.status_code < 500 else log.error
    log_method(
        "app.exception",
        error_type=exc.error_type,
        detail=str(exc),
        status=exc.status_code,
        exc_info=exc.status_code >= 500,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://api.example.com/errors/{exc.error_type}",
            "title": exc.title,
            "status": exc.status_code,
            "detail": str(exc),
            "instance": str(request.url.path),
            "request_id": request_id,
        },
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
```

## Pydantic Validation Errors

Pydantic already raises `RequestValidationError`. A custom handler converts it to the RFC 7807 format with an `errors[]` array.

## Unexpected Errors

`Exception` is caught last. It is logged with a traceback, and the client gets a generic message with no internal details:

```json
{
  "type": "https://api.example.com/errors/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred",
  "instance": "/api/v1/...",
  "request_id": "..."
}
```

## Prohibitions

- Routers **must not** catch and re-wrap exceptions: that is the handler's job
- Services **must not** raise `HTTPException` directly
- `pass` inside `except` is a code smell: it catches everything and ignores it. Only do it deliberately, with a log
- Catching a top-level `Exception` anywhere other than `unexpected_error_handler` is not allowed
