import datetime
from typing import Annotated, Any, Literal, NamedTuple, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from ecommerce.core.exceptions.base import ValidationFailedError
from ecommerce.core.pagination.cursor import CursorKey, CursorParams, decode_cursor
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


class ProductListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    brand_id: UUID | None
    category_id: UUID
    price: int = Field(description="Lowest price among the matching variants")


class Position(NamedTuple):
    price: int | None
    id: UUID


OptionFilter = Annotated[str, StringConstraints(pattern=r"^[^:]+:.+$", max_length=151)]


class ProductQuery(CursorParams):
    category_id: UUID | None = Field(None, description="Includes subcategories")
    brand_id: UUID | None = None
    min_price: Money | None = None
    max_price: Money | None = None
    option: list[OptionFilter] = Field(
        default_factory=list,
        max_length=10,
        description="`name:value`; one variant must match all of them",
    )
    sort: Literal["newest", "price_asc", "price_desc"] = "newest"

    @model_validator(mode="after")
    def check(self) -> Self:
        if len(self.options) < len(self.option):
            raise ValueError("each option name may appear once")
        low, high = self.min_price, self.max_price
        if low is not None and high is not None and low > high:
            raise ValueError("min_price must not exceed max_price")
        return self

    @property
    def options(self) -> dict[str, str]:
        pairs = (pair.partition(":") for pair in self.option)
        return {name: value for name, _, value in pairs}

    def filters(self) -> dict[str, object]:
        """What the total depends on: no sort, limit or cursor."""
        fields = {"category_id", "brand_id", "min_price", "max_price"}
        return self.model_dump(include=fields) | {"options": self.options}

    def after(self) -> Position | None:
        """Decode the cursor; it must come from a page with the same sort."""
        if self.cursor is None:
            return None
        price: int | None = None
        newest = self.sort == "newest"
        match decode_cursor(self.cursor):
            case [str() as last_id] if newest:
                pass
            case [int() as price, str() as last_id] if not newest:
                pass
            case _:
                raise ValidationFailedError("Invalid cursor")
        try:
            return Position(price, UUID(last_id))
        except ValueError:
            raise ValidationFailedError("Invalid cursor") from None

    def cursor_key(self, row: Any) -> CursorKey:
        if self.sort == "newest":
            return [str(row.id)]
        return [row.price, str(row.id)]


variant_list = TypeAdapter(list[VariantRead])
product_list = TypeAdapter(list[ProductListItem])
