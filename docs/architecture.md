# Architecture

> Status: partially implemented

Implemented today: nested settings (`config/settings.py`), the DB base (`core/db`), base exceptions with RFC 7807 handlers (`core/exceptions`), structlog logging and request id middleware (`core/observability`), the health endpoint (`api/health.py`), the app factory (`main.py`), Alembic in `migrations/`, and tests with testcontainers. The rest of this document describes the target architecture.

This document is the entry point to the project's architecture documentation.

## Goals

- Production-grade ecommerce REST API
- A codebase that can serve as a **template** for future projects
- A demonstration of SOLID, Clean Architecture, and design patterns
- Clean, maintainable, extensible code

## Documents

### Foundation

- [Project Structure](architecture/structure.md) - folder layout, module template
- [Layers & Flow](architecture/layers-and-flow.md) - Router → Service → Repository → UoW
- [SOLID & Patterns](architecture/solid-and-patterns.md) - where and how the principles and patterns are applied
- [Database](architecture/database.md) - Base, mixins, migrations, transactions

### Cross-cutting

- [Error Handling](architecture/error-handling.md) - exception hierarchy, RFC 7807
- [Security](architecture/security.md) - auth, authz, password, headers, secrets
- [Observability](architecture/observability.md) - logs, metrics, tracing, health
- [Domain Events](architecture/domain-events.md) - in-process event bus

### Infrastructure

- [Caching & Background Tasks](architecture/caching-and-tasks.md) - Redis, Taskiq
- [Rate Limiting](architecture/rate-limiting.md) - custom middleware
- [Testing](architecture/testing.md) - strategy, factories, testcontainers
- [Deployment](architecture/deployment.md) - Dockerfile, CI/CD, envs

### Usage

- [Reusability as Template](architecture/reusability.md) - adapting it to a new project

### Architecture Decision Records

- [ADRs](adr/README.md) - a log of key architectural decisions

## Stack

| Layer | Tool |
|-------|------|
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic[tz] |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Logging | structlog |
| Background tasks | Taskiq |
| Cache | Redis |
| Observability | OpenTelemetry Collector -> Tempo (traces), Loki (logs), Prometheus (metrics), Grafana |
| Auth | PyJWT + argon2-cffi |
| Package manager | uv |
| Linter/Formatter | ruff |
| Type checking | mypy |
| Testing | pytest-asyncio + httpx + polyfactory + testcontainers |
| Containerization | Docker + Docker Compose |

## Principles

1. **Layered architecture** - strict dependency direction: HTTP → Service → Repo → DB
2. **Dependency inversion** - services depend on Protocol abstractions, not on the ORM
3. **Modular organization** - each domain (`brands`, `orders`) is self-contained
4. **Pure domain core, fat infrastructure** - business logic without the framework
5. **Explicit transactions** - transaction management in one place (Unit of Work)
6. **Fail loudly, recover deliberately** - domain exceptions, a single error format
7. **Observable by default** - structured logs and traces out of the box
8. **Reusable framework, replaceable domain** - `core/` stays unchanged, `modules/` is the domain
