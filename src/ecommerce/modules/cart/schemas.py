from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, computed_field


class CartItemAdd(BaseModel):
    variant_id: UUID
    quantity: int = Field(1, ge=1, le=1000)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=1000)


class CartLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    product_id: UUID
    name: str
    sku: str
    options: dict[str, Any]
    unit_price: int
    quantity: int
    stock: int
    # Folded into `available`; not part of the response.
    is_active: bool = Field(exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def line_total(self) -> int:
        return self.unit_price * self.quantity

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> bool:
        return self.is_active and self.stock >= self.quantity


class CartRead(BaseModel):
    items: list[CartLine]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> int:
        return sum(line.line_total for line in self.items)


cart_lines = TypeAdapter(list[CartLine])
