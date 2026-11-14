# Deployment

> Status: partially implemented
>
> Exists today: a multi-stage uv `Dockerfile` (non-root user, no migrations on startup), `compose.yaml` with PostgreSQL, `make up`, `make down`, `make migrate`, `make run`, and GitHub Actions CI in `.github/workflows/ci.yml` (`uv sync --locked`, `make check`, `make test`, docker build).

## Dockerfile

Multi-stage, non-root user, minimal final image:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
RUN useradd --system --uid 1000 app && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app src/ ./src/
COPY --chown=app:app migrations/ ./migrations/
COPY --chown=app:app alembic.ini ./
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -f http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "fastapi_ecommerce_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Principles:

- **Multi-stage**: the final image contains neither uv nor build deps
- **Non-root user**: `USER app`, protection against container escape
- **Minimal base**: `python:3.12-slim` (~80MB), not `python:3.12` (~1GB)
- **No cache** in pip / apt: smaller size
- **Health check**: Docker and K8s know the process is alive
- `--frozen`: exact versions from the lock file, no surprise updates

## Docker Compose

`compose.yaml` for dev, extended to a full stack:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin
      POSTGRES_DB: ecommerce
    volumes: [postgres-data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin"]
      interval: 5s

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports: ["4317:4317"]   # OTLP gRPC from the app
    depends_on: [tempo, loki]

  tempo:
    image: grafana/tempo:latest     # traces

  loki:
    image: grafana/loki:latest      # logs

  prometheus:
    image: prom/prometheus:latest   # metrics
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    depends_on: [tempo, loki, prometheus]

  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]

volumes:
  postgres-data:
```

Locally, the app runs **outside compose** for hot reload: `uv run fastapi dev src/fastapi_ecommerce_api/main.py`. Compose brings up only the dependencies.

## Environments

| stage | how it is deployed |
|-------|--------------------|
| `local` | `docker compose up` + `uv run fastapi dev` |
| `dev` | container on a server, secrets from CI |
| `staging` | k8s, secrets from vault, production-like environment |
| `production` | k8s, blue-green / rolling update |

The `SERVICE__STAGE` env var is the single source of truth about the environment. `Settings.service.stage` is used in code for feature flags and conditional initialization (debug logging only in `local`/`dev`).

## Migrations in CI/CD

Migrations are **not run at app startup**. They are a separate pipeline step:

```bash
alembic upgrade head    # before deploying the new version
```

Otherwise, during a rolling update several pods would try to migrate at the same time, causing a conflict. In k8s this is usually implemented as a **Job** (a one-off task) before scaling the deployment.

For backwards-incompatible migrations, use two stages:

1. Deploy version N+1, which supports both schemas
2. Apply the migration
3. Deploy version N+2, which works only on the new schema

This allows zero downtime even when the structure changes.

## CI: GitHub Actions

```yaml
name: ci
on: [push, pull_request]
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: {POSTGRES_USER: test, POSTGRES_PASSWORD: test, POSTGRES_DB: test}
        ports: ["5432:5432"]
        options: --health-cmd "pg_isready -U test"
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src/fastapi_ecommerce_api
      - run: uv run pytest --cov=fastapi_ecommerce_api --cov-fail-under=85
      - run: uv run pip-audit
```

A separate job builds & pushes the Docker image on push to main / on a tag.

## Pre-commit

Locally, the same checks plus:

- `gitleaks`: scans for leaked secrets
- `commitizen` or `conventional-commits-lint`: for formalized commit messages

## Releases

- **Semver** via tags (`v1.2.3`)
- **CHANGELOG.md** via `git-cliff` (generated from conventional commits)
- On a tag push, the workflow builds a Docker image with the version tag, pushes it to the registry, and optionally creates a GitHub Release

## Observability config in production

See [Observability](observability.md). Minimum:

- OTLP endpoint on the OpenTelemetry Collector, which routes traces to Tempo, logs to Loki, and metrics to Prometheus (viewed in Grafana)
- Prometheus scrapes `/metrics`
- structlog in JSON mode -> stdout -> cluster log aggregator

## Secrets

See [Security -> Secrets Management](security.md#secrets-management).

## Scaling

- The app is stateless: scale horizontally by adding pods
- Sticky sessions are not needed (stateless JWT)
- DB: vertical scale + read replicas (via an `engine` with two URLs and read/write routing)
- Background workers: a separate deployment, scaled by queue depth
