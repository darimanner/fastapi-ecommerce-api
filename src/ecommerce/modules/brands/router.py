from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from ecommerce.core.crud import CRUDService
from ecommerce.core.pagination.offset import OffsetParams, Page
from ecommerce.modules.brands.models import Brand
from ecommerce.modules.brands.schemas import (
    BrandCreate,
    BrandRead,
    BrandUpdate,
    brand_list,
)
from ecommerce.uow import UoW

type BrandService = CRUDService[Brand, BrandCreate, BrandUpdate]


def get_service(uow: UoW) -> BrandService:
    return CRUDService(uow, lambda: uow.brands)


Service = Annotated[BrandService, Depends(get_service)]

router = APIRouter(prefix="/brands", tags=["brands"])
admin_router = APIRouter(prefix="/admin/brands", tags=["admin"])


@router.get("")
async def list_brands(
    service: Service, params: Annotated[OffsetParams, Query()]
) -> Page[BrandRead]:
    return Page.from_slice(await service.list_offset(params), brand_list)


@router.get("/{brand_id}", response_model=BrandRead)
async def get_brand(service: Service, brand_id: UUID) -> Brand:
    return await service.get(brand_id)


@admin_router.post("", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(service: Service, payload: BrandCreate) -> Brand:
    return await service.create(payload)


@admin_router.put("/{brand_id}", response_model=BrandRead)
async def replace_brand(service: Service, brand_id: UUID, payload: BrandCreate) -> Brand:
    return await service.replace(brand_id, payload)


@admin_router.patch("/{brand_id}", response_model=BrandRead)
async def update_brand(service: Service, brand_id: UUID, payload: BrandUpdate) -> Brand:
    return await service.update(brand_id, payload)


@admin_router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(service: Service, brand_id: UUID) -> None:
    await service.delete(brand_id)
