import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter

from fastapi_ecommerce_api.core.slug import Name, NamedSluggedCreate, Slug


class CategoryCreate(NamedSluggedCreate):
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None
    parent_id: UUID | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


category_list = TypeAdapter(list[CategoryRead])
