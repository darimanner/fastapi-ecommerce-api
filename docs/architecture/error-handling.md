# Error Handling

> Status: partially implemented
>
> Implemented: the exception hierarchy, RFC 7807 handlers and database error mapping below. Planned: `UnauthorizedError`, `ForbiddenError` and `RateLimitedError`, added with auth and rate limiting.

## Principles

- Services raise **domain** exceptions, not `HTTPException`
- One set of global handlers translates them to HTTP using the **RFC 7807 Problem Details** format
- No "magic" `Exception("smth went wrong")`
- 5xx errors are logged with a traceback; 4xx errors are only a warning, with no alert
- Driver messages, SQL and submitted values never reach the client

## Hierarchy

`core/exceptions/base.py`:

```python
class AppError(Exception):
    status_code = 500
    title = "Internal Server Error"

    def __init__(self, detail: str | None = None, **extra: object) -> None:
        self.detail = detail or self.title
        # Extra problem fields (RFC 7807 extension members), e.g. `errors`.
        self.extra = extra
        super().__init__(self.detail)


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
```

Modules inherit from these and only set the detail:

```python
# src/fastapi_ecommerce_api/modules/brands/exceptions.py
class BrandNotFoundError(NotFoundError):
    def __init__(self, brand_id: UUID) -> None:
        super().__init__(f"Brand {brand_id} does not exist")
```

## RFC 7807 Problem Details

All HTTP errors share one format with the media type `application/problem+json`. `type` is derived from `title` (`"Not Found"` becomes `"not-found"`):

```json
{
  "type": "not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Brand 0193... does not exist",
  "instance": "/api/v1/brands/0193...",
  "request_id": "5f8b1e..."
}
```

`request_id` comes from the structlog context bound by the request middleware, which links the error a client sees to the server logs. Extension members passed as `AppError(..., errors=[...])` are added to the body; validation failures use them:

```json
{
  "type": "validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "Validation Error",
  "instance": "/api/v1/brands",
  "request_id": "...",
  "errors": [{"field": "body.name", "message": "String should have at least 1 character"}]
}
```

## Handlers

`core/exceptions/handlers.py` registers, via `register_exception_handlers(app)`:

| Exception | Handler | Response |
|-----------|---------|----------|
| `AppError` | `app_error_handler` | its status, title, detail and extension members |
| `IntegrityError` | `integrity_error_handler` | mapped by `map_integrity_error`, see below |
| `HTTPException` | `http_error_handler` | its status with the standard phrase as title |
| `RequestValidationError` | `validation_error_handler` | 422 with `errors[]` |
| any other exception | `unexpected_error_handler` (called by the request middleware) | generic 500 |

## Database errors

Services do not pre-check uniqueness or references with extra queries: the database enforces them, and `map_integrity_error` in `core/exceptions/db.py` turns the violation into a client error. It reads the asyncpg error behind SQLAlchemy's `IntegrityError` (`sqlstate`, `constraint_name`, `table_name`, `column_name`, `detail`). Field names come from the `Key (...)=` part of the detail; values are dropped.

| sqlstate | Error | Response |
|----------|-------|----------|
| `23505` unique | `ConflictError("<field> already exists")` | 409, `errors: [{"field", "message": "already exists"}]` |
| `23503` foreign key on delete ("is still referenced") | `ConflictError("Resource is still referenced by <table>")` | 409 |
| `23503` foreign key on insert or update | `ValidationFailedError("Referenced <field> does not exist")` | 422, `errors: [{"field", "message": "does not exist"}]` |
| `23514` check | `ValidationFailedError("Constraint <name> failed")`, name without the `ck_<table>_` prefix | 422 |
| `23502` not null | `ValidationFailedError("<column> is required")` | 422 |
| anything else | `AppError()` | generic 500; the original error is logged |

Constraint names are predictable thanks to the naming convention on `Base` (see [Database](database.md)), which is what makes the check mapping readable.

## Unexpected Errors

Any other exception is logged with a traceback, and the client gets a generic body with no internal details:

```json
{
  "type": "internal-server-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Internal Server Error",
  "instance": "/api/v1/...",
  "request_id": "..."
}
```

## Prohibitions

- Routers **must not** catch and re-wrap exceptions: that is the handlers' job
- Services **must not** raise `HTTPException` directly
- `pass` inside `except` is a code smell: it catches everything and ignores it. Only do it deliberately, with a log
- Catching a top-level `Exception` anywhere other than the request middleware is not allowed
