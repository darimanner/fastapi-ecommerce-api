# Rate Limiting

> Status: planned

## State of the libraries in 2026

| Library | Status | Notes |
|---------|--------|-------|
| `slowapi` | active, used in production | "alpha quality" in the README, decorator-based, requires an explicit `request` parameter in every endpoint |
| `fastapi-limiter` | low activity | last release > 12 months ago, effectively abandoned |
| `asgi-ratelimit` | maintained, Redis-only | centralized rules, ASGI middleware |

## Project decision: custom middleware

Why build our own instead of using a library:

1. Full control over the key strategy (IP, user, endpoint, combination)
2. Correct `X-RateLimit-*` headers (Limit, Remaining, Reset)
3. RFC 7807 in the error body (like everywhere else in the project)
4. Demonstrates an understanding of the mechanism for the portfolio
5. No hard dependency on a half-abandoned package

Implementation size: 150-250 lines. Fully covered by tests.

## Algorithm: Sliding Window Counter

More accurate than a fixed window (no burst problem at the window boundary), lighter than a sliding log (does not store every request).

The idea: look at the **current window + a weighted part of the previous one**:

```
weight = 1 - (time_in_current_window / window_size)
count = current_window_count + previous_window_count * weight
```

In Redis via an atomic pipeline:

```
INCR key
EXPIRE key window_seconds NX  (only if the key is new)
GET key_previous
```

## Structure

```
core/rate_limiter/
├── middleware.py    # ASGI middleware, entry point
├── strategies.py    # KeyStrategy: ByIP, ByUser, ByIPAndPath
├── backend.py       # RateLimitBackend Protocol + RedisRateLimitBackend
└── policies.py      # RateLimitPolicy(limit, window, strategy)
```

## Configuration

In `config/settings.py`:

```python
class RateLimitSettings(BaseModel):
    enabled: bool = True
    default_policy: str = "100/minute"  # global fallback
    auth_login_policy: str = "5/minute"  # stricter for login
    auth_register_policy: str = "3/hour"
```

Per-route override via a dependency:

```python
@router.post("/login", dependencies=[Depends(RateLimit("5/minute", by="ip"))])
async def login(...): ...
```

## Response headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1700003600
Retry-After: 27        # only on 429
```

## 429 error body

In RFC 7807 format (like all other errors):

```json
{
  "type": "https://api.example.com/errors/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded: 5 per 60 seconds",
  "instance": "/api/v1/auth/login",
  "request_id": "..."
}
```

## Tests

- **Unit**: `RateLimitBackend` is replaced with a deterministic in-memory one, and edge cases are checked (window boundary, exceeding the limit)
- **Integration**: testcontainers with a real Redis

## Alternative: keep the ready-made library option open

The `RateLimitBackend` + middleware architecture allows swapping the implementation without changing routers. If the custom one turns out to be overkill for a specific use case, switch to `slowapi` through an adapter.

## ATTENTION: distributed deployment

Rate limiting on Redis works correctly for multi-pod deployments (shared counter). The in-memory backend is **for dev only**. In production without Redis, each pod counts separately, so the effective limit is multiplied by the number of pods.
