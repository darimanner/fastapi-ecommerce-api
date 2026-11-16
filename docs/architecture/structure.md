# Project Structure

> Status: partially implemented

Implemented today under `src/ecommerce/`: `config/settings.py`, `main.py`, `api/health.py`, `core/db/` (`model.py`, `sessions.py`, `mixins/timestamp.py`, `mixins/uuid_pk.py`), `core/exceptions/` (`base.py`, `handlers.py`, `db.py`), `core/pagination/`, `core/observability/` (`logging.py`, `middleware.py`), `core/crud.py`, `core/slug.py`, `core/redis.py`, `core/counts.py`, `interfaces/` (`repository.py`, `unit_of_work.py`), `infrastructure/` (`repository.py`, `unit_of_work.py`), `uow.py`, `cache.py`, and the `brands`, `categories` and `products` modules. The rest of the tree is the target layout.

The approach is a **modular monolith**: each domain lives in its own folder and is self-contained. This improves cohesion, makes it easier to extract a module into a separate service later, and keeps feature work local.

## Tree

```
src/ecommerce/
├── config/
│   └── settings.py           # pydantic-settings: Settings root + sub-models
├── main.py                   # FastAPI app factory (create_app), middleware, lifespan
├── uow.py                    # AppUnitOfWork: composition root of module repositories
├── cache.py                  # CatalogCounts: count cache shared by catalog modules
│
├── core/                     # Framework code - reused as is
│   ├── db/
│   │   ├── model.py          # Base + MetaData with naming convention
│   │   ├── sessions.py       # async_sessionmaker, get_db dependency
│   │   └── mixins/
│   │       ├── uuid_pk.py    # UUIDv7 primary key
│   │       ├── timestamp.py
│   │       ├── soft_delete.py
│   │       └── audit.py
│   ├── exceptions/
│   │   ├── base.py           # AppError + hierarchy
│   │   ├── db.py             # IntegrityError -> 409/422 mapping
│   │   └── handlers.py       # FastAPI handlers (RFC 7807)
│   ├── events/
│   │   ├── bus.py            # In-process EventBus
│   │   └── base.py           # DomainEvent base
│   ├── redis.py              # Redis client, get_redis dependency
│   ├── counts.py             # VersionedCounts: cached totals invalidated by INCR
│   ├── cache/
│   │   ├── backend.py        # AbstractCache Protocol
│   │   └── redis.py          # RedisCache
│   ├── security/
│   │   ├── jwt.py            # encode/decode tokens
│   │   ├── passwords.py      # argon2 hash/verify
│   │   └── headers.py        # security headers middleware
│   ├── crud.py               # CRUDService[Model, Create, Update]
│   ├── slug.py               # slugify, Slug/Name types, name+slug create schema
│   ├── pagination/
│   │   ├── offset.py         # OffsetParams, Page[T]
│   │   └── cursor.py         # CursorParams, CursorPage[T], cursor encoding
│   ├── observability/
│   │   ├── logging.py        # structlog setup
│   │   ├── middleware.py     # request id
│   │   ├── tracing.py        # OpenTelemetry
│   │   └── metrics.py        # Prometheus
│   ├── rate_limiter/
│   │   ├── middleware.py
│   │   ├── strategies.py     # by_ip, by_user
│   │   └── backend.py
│   └── deps/                 # Cross-cutting DI (current_user, etc.)
│
├── api/
│   └── health.py             # Health endpoint
│
├── interfaces/               # Protocol contracts - the core's public API
│   ├── repository.py         # Repository[T], Slice[T]
│   ├── unit_of_work.py       # UnitOfWork
│   └── cache.py              # CacheBackend
│
├── infrastructure/           # Generic SQLAlchemy implementations
│   ├── repository.py         # SQLAlchemyRepository[Model]
│   └── unit_of_work.py       # SQLAlchemyUnitOfWork
│
└── modules/                  # Domain modules - standalone units
    ├── auth/                 # cross-cutting (used by other modules)
    ├── brands/
    ├── categories/
    ├── products/
    └── orders/
```

## Module template

A module holds only the files it needs. `brands` is model, schemas, repository and router, with CRUD from `CRUDService`; `categories` adds `service.py` and `exceptions.py` for the tree rules; `products` holds two models (a product and its variants) with a service each. The full set of files a module may have:

```
modules/{name}/
├── __init__.py
├── router.py        # APIRouter, HTTP endpoints
├── service.py       # Business logic, orchestration
├── repository.py    # Concrete repository on top of SQLAlchemyRepository
├── models.py        # SQLAlchemy ORM model(s) of this module
├── schemas.py       # Pydantic DTOs: Create, Update, Read
├── deps.py          # Module-level DI: get_service, get_repo
├── exceptions.py    # Module-specific exceptions (inherit core AppError)
└── events.py        # Domain events of this module
```

## Dependency rules

```
modules/* ─────► interfaces/* ◄───── infrastructure/*
                                    core/*
```

- `modules/` imports `interfaces/` and `core/`
- `infrastructure/` implements `interfaces/`
- `core/` knows nothing about `modules/`
- `interfaces/` depends only on the stdlib and Pydantic

**No imports between modules.** `modules/orders/` does not import `modules/products/` directly. If data from another module is needed, use **events** or **shared interfaces** (for example, `OrderService` takes a `ProductReadRepository` in its constructor; who passed it in is not its concern).

The exception is `auth/`: its `get_current_user` dependency is used by all protected endpoints. This is a deliberate simplification for a pet project; in a larger project it would be a separate shared kernel.

## Models by module

Models live in `modules/brands/models.py`, not in a global `infrastructure/models/` folder. This:

- Improves cohesion (everything about a brand is in one folder)
- Makes it easier to extract the module into a separate service
- Keeps feature work local

`migrations/env.py` calls `import_all_models()` (`modules/__init__.py`), which imports every `modules/*/models.py`, so Alembic sees all tables without a manual list.

Adding a module means: the folder, its repository in `AppUnitOfWork` (`uow.py`), its routers in `create_app()` (`main.py`), and a migration.
