from typing import Any

from pydantic import BaseModel, Field, TypeAdapter

from ecommerce.interfaces.repository import Slice


class OffsetParams(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class Page[T](BaseModel):
    items: list[T]
    has_next: bool
    total: int | None = None

    @classmethod
    def from_slice(
        cls, slice_: Slice[Any], adapter: TypeAdapter[list[T]], total: int | None = None
    ) -> Page[T]:
        # One adapter call validates the whole batch; construct skips a second pass.
        items = adapter.validate_python(slice_.items, from_attributes=True)
        return cls.model_construct(items=items, has_next=slice_.has_next, total=total)
