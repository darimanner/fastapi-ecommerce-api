# Project Structure

> Status: partially implemented

Implemented today under `src/fastapi_ecommerce_api/`: `config/settings.py`, `main.py`, `api/health.py`, `core/db/` (`model.py`, `sessions.py`, `mixins/timestamp.py`), `core/exceptions/` (`base.py`, `handlers.py`), and `core/observability/` (`logging.py`, `middleware.py`). The rest of the tree is the target layout.

The approach is a **modular monolith**: each domain lives in its own folder and is self-contained. This improves cohesion, makes it easier to extract a module into a separate service later, and keeps feature work local.

## Tree

```
src/fastapi_ecommerce_api/
├── config/
│   └── settings.py           # pydantic-settings: Settings root + sub-models
├── main.py                   # FastAPI app factory (create_app), middleware, lifespan
│
├── core/                     # Framework code - reused as is
│   ├── db/
│   │   ├── model.py          # Base + MetaData with naming convention
│   │   ├── sessions.py       # async_sessionmaker, get_db dependency
│   │   ├── unit_of_work.py   # SQLAlchemyUnitOfWork
│   │   └── mixins/
│   │       ├── timestamp.py
│   │       ├── soft_delete.py
│   │       └── audit.py
│   ├── exceptions/
│   │   ├── base.py           # AppError + hierarchy
│   │   └── handlers.py       # FastAPI handlers (RFC 7807)
│   ├── events/
│   │   ├── bus.py            # In-process EventBus
│   │   └── base.py           # DomainEvent base
│   ├── cache/
│   │   ├── backend.py        # AbstractCache Protocol
│   │   └── redis.py          # RedisCache
│   ├── security/
│   │   ├── jwt.py            # encode/decode tokens
│   │   ├── passwords.py      # argon2 hash/verify
│   │   └── headers.py        # security headers middleware
│   ├── pagination/
│   │   ├── offset.py         # OffsetPagination, Page[T]
│   │   └── cursor.py         # CursorPagination
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
│   ├── repository.py         # ReadRepository, WriteRepository, CRUDRepository
│   ├── unit_of_work.py       # AbstractUnitOfWork
│   └── cache.py              # CacheBackend
│
├── infrastructure/           # Generic SQLAlchemy implementations
│   └── repository.py         # SQLAlchemyRepository[Model]
│
└── modules/                  # Domain modules - standalone units
    ├── auth/                 # cross-cutting (used by other modules)
    ├── brands/
    ├── categories/
    ├── products/
    └── orders/
```

## Module template

Every module repeats the same structure:

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

Target: `migrations/env.py` imports all models through an `import_all_models()` utility, which walks `src/fastapi_ecommerce_api/modules/*/models.py`, so Alembic sees all tables without a manual list.
