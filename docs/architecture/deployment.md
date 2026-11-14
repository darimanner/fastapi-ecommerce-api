# Deployment

> Status: partially implemented
>
> Exists today: a multi-stage uv `Dockerfile` (non-root user, no migrations on startup), `compose.yaml` with PostgreSQL, `make up`, `make down`, `make migrate`, `make run`, and GitHub Actions CI in `.github/workflows/ci.yml` (`uv sync --locked`, `make check`, `make test`, docker build).

## Dockerfile

See [`Dockerfile`](../../Dockerfile). Principles:

- **Multi-stage**: dependencies are installed in a builder stage with uv; the final image has the virtualenv but not uv or build caches
- **Non-root user**: `USER app`, protection against container escape
- **Minimal base**: `python:3.14-slim`
- **Reproducible**: `uv sync --locked`, exact versions from the lock file
- **Health check** without curl: a `python -c` probe of `/health/live`
- **No migrations on startup**: see [Migrations in CI/CD](#migrations-in-cicd)

## Docker Compose

[`compose.yaml`](../../compose.yaml) runs the dependencies for local development. Today it has PostgreSQL only; the target stack adds:

| Service | Purpose |
|---------|---------|
| `redis` | cache, rate limiting, Taskiq broker |
| `otel-collector` | receives OTLP traces and logs from the app |
| `tempo` | traces |
| `loki` | logs |
| `prometheus` | metrics, scrapes `/metrics` |
| `grafana` | dashboards with log and trace correlation |

The observability services run under a compose profile (`docker compose --profile observability up`), so the default `make up` stays light.

Locally, the app runs **outside compose** for hot reload: `make run`. Compose brings up only the dependencies.

## Environments

| stage | how it is deployed |
|-------|--------------------|
| `local` | `make up` + `make run` |
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

See [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml): on every pull request and push to `main` it runs `uv sync --locked`, `make check` (ruff, mypy, lock check), `make test` (testcontainers PostgreSQL, 85% coverage gate) and `docker build`.

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
