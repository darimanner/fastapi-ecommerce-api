import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter

from ecommerce.core.slug import Name, NamedSluggedCreate, Slug


class BrandCreate(NamedSluggedCreate):
    pass


class BrandUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


brand_list = TypeAdapter(list[BrandRead])
