# Caching & Background Tasks

> Status: partially implemented

Implemented: Redis (`core/redis.py`) and the count cache (`core/counts.py`). Planned: the `CacheBackend` abstraction, entity caching and background tasks.

## Count cache

The storefront product listing returns an exact `total` without `count(*)` per page ([ADR-0003](../adr/0003-pagination-without-count.md)). `VersionedCounts(redis, namespace)` caches one total per filter set:

- Key: `counts:<namespace>:<version>:<sha256 of the filters>`, TTL one hour. Sort, limit and cursor are not part of the filters, so every page of one listing shares a total.
- Invalidation: `bump()` runs `INCR counts:<namespace>:version` after every commit that can change a total. Old keys are never read again and expire by TTL; there is no `SCAN`/`DEL` over patterns.
- Order: the version is read before the count query. If a write commits after that read, its bump retires the key, so a total that misses the write is never served once the bump has run. Between a commit and its bump (one Redis round trip) the old total may still be served.
- Connections: the cache is read and written outside the Unit of Work; only a cache miss opens a session, for the count query itself. A slow Redis never pins a pooled database connection.
- Key space: every distinct filter set is a key, so a client walking many price ranges creates many short-lived keys and count queries. The TTL bounds the memory; rate limiting (planned) bounds the queries.
- Writers: `CRUDService._after_write()` bumps for products, variants and categories (a category move changes which products a category filter covers). The services get the `catalog` instance through `CatalogCounts` (`src/ecommerce/cache.py`), so modules share a namespace without importing each other.
- Redis down: reads return `total: null` (the page itself still works), a failed bump logs `counts.bump_failed` and totals may be stale for up to the TTL. The client has 1 s socket timeouts, so a hung Redis slows a request instead of hanging it.

## Cache

### Abstraction

```python
# interfaces/cache.py
class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def delete_pattern(self, pattern: str) -> int: ...
    async def ping(self) -> bool: ...
```

Implementations:

- `core/cache/redis.py`: `RedisCache(redis.asyncio.Redis)`
- `core/cache/memory.py`: `InMemoryCache` for unit tests

Services depend on `CacheBackend`, not on Redis. This makes it possible to:

- Swap in the in-memory cache in tests
- Move to another backend (Memcached, Hazelcast) without touching services

### Usage

```python
class ProductService:
    def __init__(self, uow: UnitOfWork, cache: CacheBackend) -> None:
        self._uow = uow
        self._cache = cache

    async def get(self, id: int) -> Product | None:
        if cached := await self._cache.get(f"product:{id}"):
            return ProductRead.model_validate_json(cached)
        async with self._uow:
            product = await self._uow.products.get(id)
        if product:
            await self._cache.set(
                f"product:{id}",
                ProductRead.model_validate(product).model_dump_json().encode(),
                ttl=300,
            )
        return product
```

### Invalidation via events

Event subscribers clear the cache:

```python
async def invalidate_product_cache(event: ProductUpdated) -> None:
    await cache.delete(f"product:{event.product_id}")
    await cache.delete_pattern("product:list:*")
```

This keeps cache invalidation separate from ProductService: it knows nothing about the cache except for reading.

### What NOT to cache

- User-specific data with PII (or with an explicit `user_id` in the key and a short TTL)
- Data sensitive to staleness (inventory counts, balance)
- Results with a wide spread of keys (cache miss > cache hit)

### HTTP caching

For GET endpoints: ETag + `Cache-Control`. A middleware computes a hash of the response body, sets `ETag`, and returns `304` on the next request with `If-None-Match`. This reduces load on the DB, not on the CDN.

## Background Tasks

### Taskiq: the recommendation for 2026

`Celery` is synchronous at its roots, with async bolted on. **Taskiq** is async-native (the same broker + worker + result backend model), with no legacy.

```python
# core/tasks/broker.py
broker = AioPikaBroker(settings.broker.url).with_result_backend(
    RedisAsyncResultBackend(settings.redis.url)
)


# modules/orders/tasks.py
@broker.task
async def send_order_confirmation_email(order_id: UUID) -> None:
    async with uow_factory() as uow:
        order = await uow.orders.get(order_id)
    await email_service.send_confirmation(order)


# usage in a handler
await send_order_confirmation_email.kiq(order.id)
```

### FastAPI BackgroundTasks vs Taskiq

| | `BackgroundTasks` | Taskiq |
|--|------------------|--------|
| Where it runs | in the same process after the response | separate worker |
| Persistent | no: lost on restart | yes: via the broker |
| Retry | no | yes |
| Good for | best-effort logs, lightweight operations | email, webhooks, invoices, reports |

**Rule**: if the task matters, use Taskiq. If "it's fine without it", use `BackgroundTasks`.

### Alternatives

- **ARQ**: a simple Redis-only async queue. If the broker is already Redis and complex routing is not needed, a fine choice with less boilerplate
- **Celery**: only if there is legacy code or you need features Taskiq lacks
- **Dramatiq**: sync-only, not suitable for an async stack

### Running the worker

```bash
uv run taskiq worker ecommerce.core.tasks.broker:broker
```

In production: a separate deployment in k8s, one or more pods, scaled by queue depth.

### Retry & idempotency

Tasks **must be idempotent**: the broker may deliver a message twice. Implementation: check a `processed_at` flag before executing, or use an `Idempotency-Key` in Redis with a TTL.

```python
@broker.task(retry_on_error=True, max_retries=3, delay=60)
async def send_email(message_id: UUID) -> None:
    if await cache.get(f"email_sent:{message_id}"):
        return  # already sent
    await email.send(message_id)
    await cache.set(f"email_sent:{message_id}", b"1", ttl=86400)
```
