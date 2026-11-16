import pytest
from redis.asyncio import Redis

from ecommerce.core.counts import VersionedCounts


class Counter:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        return self.value


@pytest.fixture
def counts(redis: Redis) -> VersionedCounts:
    return VersionedCounts(redis, "test")


async def test_total_is_counted_once_per_filters(counts: VersionedCounts) -> None:
    count = Counter(7)

    first = await counts.get_or_count({"a": 1, "b": "x"}, count)
    second = await counts.get_or_count({"b": "x", "a": 1}, count)

    assert (first, second, count.calls) == (7, 7, 1)


async def test_other_filters_are_counted_separately(counts: VersionedCounts) -> None:
    await counts.get_or_count({"a": 1}, Counter(7))

    assert await counts.get_or_count({"a": 2}, Counter(3)) == 3


async def test_bump_invalidates_every_total(counts: VersionedCounts) -> None:
    await counts.get_or_count({"a": 1}, Counter(7))

    await counts.bump()

    assert await counts.get_or_count({"a": 1}, Counter(8)) == 8


async def test_namespaces_do_not_share_versions(redis: Redis) -> None:
    catalog, other = VersionedCounts(redis, "catalog"), VersionedCounts(redis, "other")
    await catalog.get_or_count({}, Counter(7))

    await other.bump()

    assert await catalog.get_or_count({}, Counter(8)) == 7


async def test_unreachable_redis_gives_no_total_and_bump_does_not_raise() -> None:
    down = Redis.from_url("redis://127.0.0.1:1", socket_connect_timeout=0.2)
    counts = VersionedCounts(down, "test")
    count = Counter(7)

    total = await counts.get_or_count({}, count)
    await counts.bump()

    assert (total, count.calls) == (None, 0)
    await down.aclose()
