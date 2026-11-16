from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status

from ecommerce.cache import CatalogCounts
from ecommerce.modules.products.models import Product, ProductVariant
from ecommerce.modules.products.schemas import (
    ProductCreate,
    ProductDetail,
    ProductRead,
    ProductUpdate,
    VariantCreate,
    VariantRead,
    VariantUpdate,
)
from ecommerce.modules.products.service import ProductService, VariantService
from ecommerce.uow import UoW


def get_products(uow: UoW, counts: CatalogCounts) -> ProductService:
    return ProductService(uow, counts)


def get_variants(uow: UoW, counts: CatalogCounts) -> VariantService:
    return VariantService(uow, counts)


Products = Annotated[ProductService, Depends(get_products)]
Variants = Annotated[VariantService, Depends(get_variants)]
NewVariants = Annotated[list[VariantCreate], Body(min_length=1, max_length=100)]

router = APIRouter(prefix="/products", tags=["products"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(service: Products, product_id: UUID) -> Product:
    return await service.get_active(product_id)


@admin_router.post(
    "/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED
)
async def create_product(service: Products, payload: ProductCreate) -> Product:
    return await service.create(payload)


@admin_router.put("/products/{product_id}", response_model=ProductRead)
async def replace_product(
    service: Products, product_id: UUID, payload: ProductCreate
) -> Product:
    return await service.replace(product_id, payload)


@admin_router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product(
    service: Products, product_id: UUID, payload: ProductUpdate
) -> Product:
    return await service.update(product_id, payload)


@admin_router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(service: Products, product_id: UUID) -> None:
    await service.delete(product_id)


@admin_router.post(
    "/products/{product_id}/variants",
    response_model=list[VariantRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_variants(
    service: Variants, product_id: UUID, payload: NewVariants
) -> list[ProductVariant]:
    return await service.add_many(product_id, payload)


@admin_router.patch("/variants/{variant_id}", response_model=VariantRead)
async def update_variant(
    service: Variants, variant_id: UUID, payload: VariantUpdate
) -> ProductVariant:
    return await service.update(variant_id, payload)


@admin_router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(service: Variants, variant_id: UUID) -> None:
    await service.delete(variant_id)
