from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from ecommerce.config.settings import settings

# Short timeouts: a hung Redis must degrade a request, not hang it.
redis_client = Redis.from_url(
    str(settings.redis.url), socket_timeout=1, socket_connect_timeout=1
)


def get_redis() -> Redis:
    return redis_client


RedisClient = Annotated[Redis, Depends(get_redis)]
