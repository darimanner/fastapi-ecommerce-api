from typing import Annotated

from fastapi import Depends

from ecommerce.core.counts import VersionedCounts
from ecommerce.core.redis import RedisClient


def get_catalog_counts(redis: RedisClient) -> VersionedCounts:
    """Totals of catalog listings; every product, variant or category write bumps it."""
    return VersionedCounts(redis, "catalog")


CatalogCounts = Annotated[VersionedCounts, Depends(get_catalog_counts)]
