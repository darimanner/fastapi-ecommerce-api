# Database

> Status: partially implemented

Implemented: `Base` with the naming convention, sessions, `TimestampMixin`, `UUIDPrimaryKeyMixin`, the generic repository, Unit of Work, pagination, database error mapping and the category tree queries. Planned: the soft delete, audit and versioned mixins, and the money type (decided with the catalog).

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

### UUIDPrimaryKeyMixin

```python
id: Mapped[uuid.UUID]  # primary key, default=uuid.uuid7
```

UUIDv7 keys are not enumerable in public URLs and stay time-ordered, so index inserts are local and keyset pagination can order by `id`. See [ADR-0002](../adr/0002-uuid7-primary-keys.md).

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
engine = create_async_engine(str(settings.database.url), pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
```

Important:

- `expire_on_commit=False` is critical for async, otherwise reading attributes after a commit triggers implicit IO
- `pool_pre_ping=True` checks the connection before use (protection against closed connections)

## Repository

`SQLAlchemyRepository[ModelT]` in `infrastructure/repository.py` implements the `Repository[T]` Protocol from `interfaces/repository.py` for any model with `UUIDPrimaryKeyMixin`:

| Method | Notes |
|--------|-------|
| `get(entity_id)` | `None` when missing; the service decides whether that is a 404 |
| `add(entity)`, `update(entity, values)`, `delete(entity)` | flush immediately, so constraint errors surface inside the service call; `update` raises `ValueError` on a key that is not a mapped field |
| `add_many(rows)` | one `INSERT ... RETURNING` for the whole batch, never a loop of `add`; rows come back in input order |
| `delete_many(entity_ids)` | one `DELETE ... WHERE id IN (...)`; returns how many rows existed and were deleted |
| `list_offset(limit, offset)`, `list_after(after, limit)` | return a `Slice`, see [Pagination](#pagination) |

Module repositories subclass it, set `model`, and build filtered queries through the protected `_slice(stmt, limit)` helper.

## Unit of Work

See [Layers & Flow](layers-and-flow.md#unit-of-work). Services receive a Unit of Work, not a session.

`UnitOfWork` in `interfaces/unit_of_work.py` declares `async with`, `commit()` and `rollback()`. `SQLAlchemyUnitOfWork` in `infrastructure/unit_of_work.py` opens a session from the injected factory on enter, calls `_init_repositories()` so subclasses can attach their repositories, and closes the session on exit, which rolls back anything not committed explicitly.

## Migrations

```bash
uv run alembic revision --autogenerate -m "add orders table"
uv run alembic upgrade head
uv run alembic downgrade -1
```

- Alembic is configured in `pyproject.toml` (`[tool.alembic]`), with `post_write_hooks` running `ruff check --fix` and `ruff format`, so migrations are formatted automatically
- `migrations/env.py` calls `import_all_models()`, which walks `src/fastapi_ecommerce_api/modules/*/models.py` and calls `importlib.import_module`, so Alembic sees all tables without a manual list
- `TimestampMixin` sets `eager_defaults`: server-set `created_at`/`updated_at` come back through `RETURNING`, so an entity stays readable after the Unit of Work has closed its session
- Migrations run as a **separate CI/CD step**, not at app startup, otherwise several pods would try to migrate in parallel

## Category tree

`categories.parent_id` is an adjacency list. Depth is limited by the `catalog.max_category_depth` setting (default 5), not by the schema. When a write sets a new parent, `CategoryService` takes a transaction-scoped advisory lock (`pg_advisory_xact_lock`), walks from the new parent to the root with a recursive CTE, and rejects the move with 409 if the node itself is on that path (a cycle) or if parent depth plus the node's subtree height exceeds the limit. The lock makes two concurrent moves check one after the other. See [ADR-0004](../adr/0004-category-tree-adjacency-list.md).

## Pagination

List endpoints never run `count(*)`: on large tables it is a full scan on every page. Repositories fetch `limit + 1` rows and return a `Slice(items, has_next)`. See [ADR-0003](../adr/0003-pagination-without-count.md).

Two strategies in `core/pagination/`, both with `limit` from 1 to 100 (default 20), used as `Annotated[OffsetParams, Query()]`:

- **Offset** (`OffsetParams`, `Page[T]`): small reference tables and admin lists
- **Cursor** (`CursorParams`, `CursorPage[T]`): large tables (products, orders); keyset on the sort key plus `id`, so deep pages cost the same as the first

```python
class Page[T](BaseModel):
    items: list[T]
    has_next: bool
    total: int | None = None  # only where a cached exact total exists


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None
```

The cursor is an opaque urlsafe base64 of a JSON list of key values, at most 512 characters. `decode_cursor` rejects anything malformed with a 422; `decode_id_cursor` additionally requires a single UUID, the key `list_after` takes.

`Page.from_slice(slice_, adapter)` and `CursorPage.from_slice(slice_, adapter, key)` convert the whole slice with one module-level `TypeAdapter(list[Schema])` call (`from_attributes=True`), never `model_validate` per row.

## Behavior on DB errors

- `IntegrityError` (unique, foreign key, check, not null) is mapped centrally to 409 or 422, see [Error Handling](error-handling.md#database-errors)
- Transactions are rolled back when the Unit of Work exits without `commit()`, including on any exception
