# AGENTS.md

Production-grade e-commerce REST API on FastAPI, SQLAlchemy 2 (async) and PostgreSQL. It is a public reference implementation: code and docs must agree, and the hard parts (transactions, concurrency, errors) must be done properly.

## Commands

```bash
make install   # uv sync + pre-commit hooks
make up        # PostgreSQL and Redis in Docker
make migrate   # alembic upgrade head
make run       # dev server on http://127.0.0.1:8000
make test      # pytest on testcontainers PostgreSQL and Redis, fails below 85% coverage (Docker required)
make check     # pre-commit: ruff, mypy --strict, uv lock check
make revision m="add brands"   # autogenerate a migration
```

`make check` runs pre-commit on tracked files only, so `git add` new files before running it.

Change dependencies only with `uv add` / `uv remove`; never edit `uv.lock` by hand.

## Layout

`src/ecommerce/` is a modular monolith, see [docs/architecture/structure.md](docs/architecture/structure.md):

- `core/`: framework code (db, exceptions, pagination, observability); knows nothing about modules
- `interfaces/`: Protocols (`Repository`, `UnitOfWork`); stdlib and Pydantic only
- `infrastructure/`: generic SQLAlchemy implementations (`SQLAlchemyRepository`, `SQLAlchemyUnitOfWork`)
- `modules/<domain>/`: one folder per domain; modules do not import each other (except `auth` dependencies)
- `uow.py`: `AppUnitOfWork`, the composition root that attaches every module's repository; routers get it through the `UoW` dependency

A module stays thin: model, schemas, repository, an explicit router, plus a service, `exceptions.py` or `events.py` only when it has real logic. No empty files. Standard CRUD comes from `core/crud.py::CRUDService`; domain rules go in its `_before_write` hook. A service that needs more than the generic repository declares a UoW Protocol with just its repositories (see `modules/categories/service.py`).

New module checklist: folder, repository in `AppUnitOfWork`, routers in `create_app()` (`main.py`), `make revision`. Reads go on `router` (`/api/v1/<name>`), writes on `admin_router` (`/api/v1/admin/<name>`); every `admin_router` gets `dependencies=[Depends(requires(Permission.<X>_WRITE))]`, and a new resource adds its permission to `modules/auth/permissions.py`.

## Conventions

- Flow: router -> service -> repository, with the transaction in a Unit of Work. Nothing persists without `await uow.commit()`.
- Services raise `AppError` subclasses (`core/exceptions/base.py`), never `HTTPException`. Responses are RFC 7807 problem+json.
- Do not pre-check uniqueness or references with extra queries: let the constraint fail; `IntegrityError` is mapped to 409/422 centrally.
- Primary keys are UUIDv7 via `UUIDPrimaryKeyMixin`.
- Lists never use `count(*)`: fetch `limit + 1` and return `has_next`; keyset pagination for large tables.
- Convert result sets with one module-level `TypeAdapter(list[Schema])` call, never `model_validate` in a loop; bulk writes with one `insert()`.
- Models are imported in `migrations/env.py` so autogenerate sees them; tests fail if a model change has no migration.
- Comments only for the non-obvious why. English everywhere.
- Architecture changes get an ADR in [docs/adr/](docs/adr/README.md); docs under `docs/architecture/` carry a status line and must match the code.

## Workflow

Branch from `main`, small commits in the Conventional Commits style, `make check` and `make test` green, pull request with squash merge. `main` is protected and requires CI.
