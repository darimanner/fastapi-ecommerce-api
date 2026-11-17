from collections.abc import Awaitable, Callable, Mapping
import hashlib
import json

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ecommerce.core.observability.logging import log

TTL_SECONDS = 3600


class VersionedCounts:
    """Cached totals per filter set; `bump()` invalidates them all at once.

    Keys embed a namespace version, so invalidation is one `INCR` and stale keys
    simply expire. Without Redis there is no total rather than a `count(*)` per page.
    """

    def __init__(self, redis: Redis, namespace: str) -> None:
        self._redis = redis
        self._prefix = f"counts:{namespace}"

    async def get_or_count(
        self, filters: Mapping[str, object], count: Callable[[], Awaitable[int]]
    ) -> int | None:
        digest = hashlib.sha256(
            json.dumps(filters, sort_keys=True, default=str).encode()
        ).hexdigest()
        try:
            # Version before count: if a write commits after this read, its bump
            # retires this key, so a total that misses the write is never served.
            version = int(await self._redis.get(f"{self._prefix}:version") or 0)
            key = f"{self._prefix}:{version}:{digest}"
            if (cached := await self._redis.get(key)) is not None:
                return int(cached)
            total = await count()
            await self._redis.set(key, total, ex=TTL_SECONDS)
        except RedisError as e:
            log.warning("counts.unavailable", error=str(e))
            return None
        return total

    async def bump(self) -> None:
        """Call after commit; on failure totals stay stale for at most the TTL."""
        try:
            await self._redis.incr(f"{self._prefix}:version")
        except RedisError as e:
            log.warning("counts.bump_failed", error=str(e))
