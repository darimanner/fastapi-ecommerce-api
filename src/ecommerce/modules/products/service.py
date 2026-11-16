from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from ecommerce.core.counts import VersionedCounts
from ecommerce.core.crud import CRUDService
from ecommerce.core.exceptions.base import NotFoundError
from ecommerce.interfaces.repository import Repository, Slice
from ecommerce.interfaces.unit_of_work import UnitOfWork
from ecommerce.modules.products.models import Product, ProductVariant
from ecommerce.modules.products.schemas import (
    ProductCreate,
    ProductQuery,
    ProductUpdate,
    VariantCreate,
    VariantUpdate,
)


class ProductCatalog(Repository[Product], Protocol):
    async def get_active(self, product_id: UUID) -> Product | None: ...

    async def list_public(self, query: ProductQuery) -> Slice[Any]: ...

    async def count_public(self, query: ProductQuery) -> int: ...


class ProductUnitOfWork(UnitOfWork, Protocol):
    @property
    def products(self) -> ProductCatalog: ...

    @property
    def variants(self) -> Repository[ProductVariant]: ...


class ProductService(CRUDService[Product, ProductCreate, ProductUpdate]):
    def __init__(self, uow: ProductUnitOfWork, counts: VersionedCounts) -> None:
        super().__init__(uow, lambda: uow.products)
        self._catalog_uow = uow
        self._counts = counts

    async def get_active(self, product_id: UUID) -> Product:
        async with self._catalog_uow as uow:
            product = await uow.products.get_active(product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} not found")
        return product

    async def list_public(self, query: ProductQuery) -> tuple[Slice[Any], int | None]:
        async with self._catalog_uow as uow:
            page = await uow.products.list_public(query)
            total = await self._counts.get_or_count(
                query.filters(), lambda: uow.products.count_public(query)
            )
        return page, total

    async def _after_write(self) -> None:
        await self._counts.bump()


class VariantService(CRUDService[ProductVariant, VariantCreate, VariantUpdate]):
    def __init__(self, uow: ProductUnitOfWork, counts: VersionedCounts) -> None:
        super().__init__(uow, lambda: uow.variants)
        self._catalog_uow = uow
        self._counts = counts

    async def add_many(
        self, product_id: UUID, variants: Sequence[VariantCreate]
    ) -> list[ProductVariant]:
        rows = [v.model_dump() | {"product_id": product_id} for v in variants]
        async with self._catalog_uow as uow:
            if await uow.products.get(product_id) is None:
                raise NotFoundError(f"Product {product_id} not found")
            created = await uow.variants.add_many(rows)
            await uow.commit()
        await self._after_write()
        return created

    async def _after_write(self) -> None:
        await self._counts.bump()
