# fastapi-ecommerce-api

[![CI](https://github.com/darimanner/fastapi-ecommerce-api/actions/workflows/ci.yml/badge.svg)](https://github.com/darimanner/fastapi-ecommerce-api/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A production-grade e-commerce REST API built with FastAPI, SQLAlchemy and PostgreSQL. It is a reference implementation: the focus is on the parts that are easy to get wrong in real shops, such as transactional checkout, stock that never oversells under concurrency, consistent error responses and observability.

## Features

Work in progress. The v1 scope:

- Catalog (done): category tree with cycle and depth checks, brands, products with variants (SKU, price, stock, options), a public listing with filters, keyset pages and totals from a Redis count cache
- Accounts (done): registration, login, refresh token rotation, `/users/me`, and role-based permissions on the admin write routes; the first admin is created with `make admin`
- Cart (done): one cart per customer with a soft stock check; lines show the current price and an `available` flag
- Checkout with stock reservation in one transaction
- Order lifecycle with a state machine and automatic expiry of unpaid reservations
- Rate limiting with a sliding window in Redis
- Observability: structured logs, traces and metrics with OpenTelemetry, Prometheus, Tempo, Loki and Grafana

## Stack

| Area | Tools |
| --- | --- |
| API | FastAPI, Pydantic v2; Typer (management CLI) |
| Database | PostgreSQL, SQLAlchemy 2 (async, asyncpg), Alembic |
| Background jobs and cache | Redis (count cache, refresh tokens); Taskiq (planned) |
| Observability | structlog; OpenTelemetry, Prometheus, Grafana (planned) |
| Tooling | uv, ruff, mypy (strict), pytest, testcontainers, Docker |

## Architecture

A modular monolith with a layered flow: router, service, repository, Unit of Work. See [docs/architecture.md](docs/architecture.md) and the [architecture decision records](docs/adr/README.md).

## Requirements

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Docker
- make

## Setup

```bash
make install
cp .env.example .env
make up
make migrate
make admin email=admin@example.com
```

`make install` sets up the git hooks, so run it inside a git repository. `make admin` creates the first admin (write routes need an admin token); it asks for the password, or reads `ADMIN_PASSWORD`.

## Make targets

| Target | What it runs |
| --- | --- |
| `make install` | `uv sync` and `pre-commit install`: dependencies and git hooks |
| `make up` | `docker compose up -d --wait`: starts PostgreSQL and Redis and waits until they are healthy |
| `make down` | `docker compose down`: stops them, the PostgreSQL data volume stays |
| `make migrate` | `alembic upgrade head`: applies all migrations |
| `make revision m="..."` | `alembic revision --autogenerate`: new migration from model changes |
| `make admin email=...` | `python -m ecommerce.cli create-admin`: creates a user with the admin role |
| `make run` | `fastapi dev`: dev server with reload on http://127.0.0.1:8000 |
| `make test` | `pytest --cov`: tests on throwaway PostgreSQL and Redis containers, fails below 85% coverage |
| `make check` | `pre-commit run --all-files`: ruff, mypy, lock check, file hygiene |

## Run

```bash
make run
```

Health checks are served at http://127.0.0.1:8000/health/live and http://127.0.0.1:8000/health/ready (pings the database).

## Checks

The tests start PostgreSQL and Redis in containers, so Docker must be running. They build the schema with the migrations and fail if the models have changes no migration covers.

```bash
make check   # pre-commit hooks: ruff, mypy, lock check
make test
```

## Migrations

Import new model modules in `migrations/env.py`, then:

```bash
make revision m="add items"
make migrate
```

New revision files are formatted with ruff automatically.

## Docker image

```bash
docker build -t fastapi-ecommerce-api .
docker run --rm -e DATABASE__URL=... -e REDIS__URL=... -e AUTH__SECRET_KEY=... fastapi-ecommerce-api alembic upgrade head
docker run -p 8000:8000 -e DATABASE__URL=... -e REDIS__URL=... -e AUTH__SECRET_KEY=... fastapi-ecommerce-api
```

Settings are loaded in full, also by `alembic upgrade head`, and `.dockerignore` excludes `.env`, so all three variables must be passed.

The image runs as a non-root user and does not migrate on startup: run migrations as a separate deploy step.

Create the first admin in a container:

```bash
docker run --rm -it -e DATABASE__URL=... -e REDIS__URL=... -e AUTH__SECRET_KEY=... fastapi-ecommerce-api python -m ecommerce.cli create-admin admin@example.com
```

`-it` is needed for the password prompt. Alternatively pass `-e ADMIN_PASSWORD` without a value: Docker takes it from your environment, so the password is not typed in the command.

## Template updates

Generated from [fastapi-service-template](https://github.com/darimanner/fastapi-service-template). Pull template changes with:

```bash
uvx copier update
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
