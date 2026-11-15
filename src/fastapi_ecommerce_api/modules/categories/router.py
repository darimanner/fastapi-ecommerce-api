from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from fastapi_ecommerce_api.config.settings import settings
from fastapi_ecommerce_api.core.pagination.offset import OffsetParams, Page
from fastapi_ecommerce_api.modules.categories.models import Category
from fastapi_ecommerce_api.modules.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    category_list,
)
from fastapi_ecommerce_api.modules.categories.service import CategoryService
from fastapi_ecommerce_api.uow import UoW


def get_service(uow: UoW) -> CategoryService:
    return CategoryService(uow, settings.catalog.max_category_depth)


Service = Annotated[CategoryService, Depends(get_service)]

router = APIRouter(prefix="/categories", tags=["categories"])
admin_router = APIRouter(prefix="/admin/categories", tags=["admin"])


@router.get("")
async def list_categories(
    service: Service, params: Annotated[OffsetParams, Query()]
) -> Page[CategoryRead]:
    return Page.from_slice(await service.list_offset(params), category_list)


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(service: Service, category_id: UUID) -> Category:
    return await service.get(category_id)


@admin_router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(service: Service, payload: CategoryCreate) -> Category:
    return await service.create(payload)


@admin_router.put("/{category_id}", response_model=CategoryRead)
async def replace_category(
    service: Service, category_id: UUID, payload: CategoryCreate
) -> Category:
    return await service.replace(category_id, payload)


@admin_router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    service: Service, category_id: UUID, payload: CategoryUpdate
) -> Category:
    return await service.update(category_id, payload)


@admin_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(service: Service, category_id: UUID) -> None:
    await service.delete(category_id)
