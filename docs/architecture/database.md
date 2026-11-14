# Database

> Status: partially implemented

Implemented today: `Base` with the naming convention (`core/db/model.py`), `engine`, `session_factory`, `get_db` and `DbSession` (`core/db/sessions.py`), `TimestampMixin` (`core/db/mixins/timestamp.py`), and Alembic in `migrations/` configured from `pyproject.toml`. The rest (other mixins, Unit of Work, pagination) is the target design.

## Base & Naming Convention

`Base` (`src/fastapi_ecommerce_api/core/db/model.py`) defines `MetaData` with a naming convention for all constraints:

```python
convention = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

Without it Alembic generates random names, and the migrations diff diverges between environments.

## Type Mapping

```python
type_annotation_map = {
    datetime.datetime: DateTime(timezone=True),
    Decimal: Numeric(precision=18, scale=4),
    dict: JSONB,
}
```

Money is always `Decimal`, never `float`. All datetimes are timezone-aware UTC.

## Mixins

All live in `src/fastapi_ecommerce_api/core/db/mixins/` and are applied as needed.

### TimestampMixin

```python
created_at: Mapped[datetime]  # server_default=func.now()
updated_at: Mapped[datetime]  # server_default=func.now(), onupdate=func.now()
```

### SoftDeleteMixin

```python
deleted_at: Mapped[datetime | None]
```

In ecommerce this is **mandatory** for `Order`, `Product`, `User`: they must not be physically deleted. The base repository filters `deleted_at IS NULL` by default. The `with_deleted()` method returns a query without the filter, for the admin panel.

### AuditMixin

```python
created_by: Mapped[UUID | None]  # FK to users.id
updated_by: Mapped[UUID | None]
```

Who created / changed the record. It is filled in `SQLAlchemyRepository` through `contextvars` (`current_user_id`), which a middleware sets.

### VersionedMixin (optional)

```python
version: Mapped[int]  # version_id_col=True in the mapper
```

Optimistic locking, for rare high-contention tables (inventory, balance).

## Sessions

`src/fastapi_ecommerce_api/core/db/sessions.py`:

```python
engine = create_async_engine(
    str(settings.database.url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
```

Important:

- `expire_on_commit=False` is critical for async, otherwise reading attributes after a commit triggers implicit IO
- `pool_pre_ping=True` checks the connection before use (protection against closed connections)

## Unit of Work

See [Layers & Flow → Unit of Work](layers-and-flow.md#unit-of-work-coredbunit_of_workpy). Services receive a UoW, not a session.

The `AbstractUnitOfWork` Protocol declares the repository attributes and the `commit/rollback` methods. The SQLAlchemy implementation opens a session in `__aenter__`, instantiates the repositories, and closes the session in `__aexit__` (with a rollback on exception).

## Migrations

```bash
uv run alembic revision --autogenerate -m "add orders table"
uv run alembic upgrade head
uv run alembic downgrade -1
```

- Alembic is configured in `pyproject.toml` (`[tool.alembic]`), with `post_write_hooks` running `ruff check --fix` and `ruff format`, so migrations are formatted automatically
- Target: `migrations/env.py` imports all models through an `import_all_models()` utility, which walks `src/fastapi_ecommerce_api/modules/*/models.py` and calls `importlib.import_module`, so Alembic sees all tables without a manual list. Until the first module exists, model modules are imported in `env.py` by hand
- Migrations run as a **separate CI/CD step**, not at app startup, otherwise several pods would try to migrate in parallel

## Pagination

Two strategies in `core/pagination/`:

- **Offset** - for the admin panel, small result sets (`page`, `limit`)
- **Cursor** - for infinite scroll, the catalog (by `(created_at, id)`)

```python
class OffsetPagination(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


class CursorPagination(BaseModel):
    cursor: str | None = None
    limit: int = Field(20, ge=1, le=100)


class Page[T](BaseModel):
    items: list[T]
    total: int | None = None  # None for cursor
    next_cursor: str | None = None
```

The base repository supports both:

```python
await repo.list(pagination=OffsetPagination(offset=0, limit=20))
await repo.list(pagination=CursorPagination(cursor="...", limit=20))
```

## Behavior on DB errors

- `OperationalError` (lost connection) → the repository raises `ServiceUnavailableError` (503)
- `IntegrityError` on a unique constraint → the repository raises `ConflictError` (409)
- Transactions are rolled back automatically when exiting the UoW on any exception
