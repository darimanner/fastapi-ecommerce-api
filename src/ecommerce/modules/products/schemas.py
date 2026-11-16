import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from ecommerce.core.slug import Name, NamedSluggedCreate, Slug

Description = Annotated[str, Field(max_length=5000)]
Sku = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
Money = Annotated[int, Field(ge=0, description="Minor units (cents)")]
Stock = Annotated[int, Field(ge=0)]
Options = Annotated[
    dict[
        Annotated[str, StringConstraints(min_length=1, max_length=50)],
        Annotated[str, StringConstraints(min_length=1, max_length=100)],
    ],
    Field(max_length=10),
]


class ProductCreate(NamedSluggedCreate):
    description: Description = ""
    brand_id: UUID | None = None
    category_id: UUID
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None
    description: Description | None = None
    brand_id: UUID | None = None
    category_id: UUID | None = None
    is_active: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str
    brand_id: UUID | None
    category_id: UUID
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class VariantCreate(BaseModel):
    sku: Sku
    price: Money
    stock: Stock = 0
    options: Options = Field(default_factory=dict)


class VariantUpdate(BaseModel):
    sku: Sku | None = None
    price: Money | None = None
    stock: Stock | None = None
    options: Options | None = None


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    sku: str
    price: int
    stock: int
    options: dict[str, str]


class ProductDetail(ProductRead):
    variants: list[VariantRead]


variant_list = TypeAdapter(list[VariantRead])
