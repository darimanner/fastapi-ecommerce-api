# Observability

> Status: partially implemented

Implemented today: structlog setup with a shared typed `log` (`core/observability/logging.py`), request ID middleware that binds `request_id` into structlog contextvars (`core/observability/middleware.py`), and a health endpoint (`api/health.py`). Tracing, metrics and the collector stack are the target design.

Three pillars: **logs**, **metrics**, **traces**. Plus health checks.

The target stack: the application exports telemetry over OTLP to an OpenTelemetry Collector, which routes it to Tempo (traces), Loki (logs) and Prometheus (metrics), with Grafana on top.

## Logging: structlog

```python
# src/fastapi_ecommerce_api/core/observability/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        mask_secrets_processor,  # masks password, token, secret
        structlog.processors.JSONRenderer()
        if not settings.logger.debug
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    cache_logger_on_first_use=True,
)
```

JSON in production, colored console in dev. All logs are structured:

```python
log.info("order.created", order_id=order.id, user_id=user.id, total=str(order.total))
```

### Request ID middleware

```python
# src/fastapi_ecommerce_api/core/observability/middleware.py
class RequestIDMiddleware:
    async def __call__(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        structlog.contextvars.bind_contextvars(
            request_id=rid,
            path=request.url.path,
            method=request.method,
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            structlog.contextvars.clear_contextvars()
```

After this, **every log event** during request handling automatically carries `request_id` without passing it explicitly.

### PII / Secrets Filtering

A processor that walks the dict arguments and masks values by the keys `password`, `token`, `secret`, `authorization`, `card_number`, `cvv`. It runs before the renderer.

## Tracing: OpenTelemetry

```python
# src/fastapi_ecommerce_api/core/observability/tracing.py
def setup_tracing(app: FastAPI) -> None:
    if not settings.telemetry.endpoint:
        return  # tracing is optional, dev can run without an OTLP collector

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.service.name,
                "service.namespace": settings.service.namespace,
                "service.version": settings.service.version,
                "deployment.environment": settings.service.stage,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=str(settings.telemetry.endpoint)))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
```

The trace ID is linked to logs through a structlog processor that adds `trace_id` and `span_id` from the current OTel context.

Locally, the OpenTelemetry Collector, Tempo, Loki, Prometheus and Grafana run in `compose.yaml`; traces are viewed in Grafana via the Tempo data source.

## Metrics: Prometheus

`prometheus-fastapi-instrumentator` + a `/metrics` endpoint. Standard metrics:

- `http_requests_total{method, path, status}`
- `http_request_duration_seconds_bucket{...}` (histogram)
- `db_pool_checked_out{}` (via `engine.pool` events)

Business metrics (added manually):

- `orders_created_total{status}`
- `payments_failed_total{provider, reason}`
- `cart_abandoned_total{}`

## Health Checks

Two endpoints, as Kubernetes requires:

```python
@router.get("/health/live", include_in_schema=False)
async def liveness() -> dict:
    """The process is alive. Always returns 200, except for a zombie process."""
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """Ready to accept traffic: DB, Redis and broker are reachable."""
    await db.execute(text("SELECT 1"))
    await cache.ping()
    return {"status": "ok", "deps": {"db": "ok", "redis": "ok"}}
```

- **Liveness fail**: K8s restarts the pod
- **Readiness fail**: removes the pod from the load balancer but does not kill it (gives it time to recover)

## Dashboards

Not part of the code, but kept in `docs/observability/`:

- Grafana dashboard JSON for the basic metrics
- Loki query examples
- Alert rules

## Trace + Log + Metric correlation

The key capability: an error response -> `request_id` -> logs in Loki -> trace in Tempo -> metrics in Grafana. Everything is linked through `request_id` and `trace_id`. This is what "observability" means.
