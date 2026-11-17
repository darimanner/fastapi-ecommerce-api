from typing import Any
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.core.db.mixins.timestamp import TimestampMixin
from ecommerce.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from ecommerce.core.db.model import Base


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    # Plain table names: modules do not import each other's models.
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(server_default="true")

    # Loaded explicitly (selectinload); a lazy load in async code would fail later.
    variants: Mapped[list[ProductVariant]] = relationship(
        lazy="raise", passive_deletes=True, order_by="ProductVariant.id"
    )


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        UniqueConstraint("product_id", "options"),
        Index(None, "options", postgresql_using="gin"),
    )

    # Variants are part of the product, so they go with it.
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    # Minor units (cents) of the store currency.
    price: Mapped[int]
    stock: Mapped[int] = mapped_column(server_default="0")
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
