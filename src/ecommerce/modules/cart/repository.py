from typing import Any, NamedTuple
from uuid import UUID, uuid7

from sqlalchemy import (
    Boolean,
    Integer,
    Row,
    String,
    Uuid,
    column,
    delete,
    func,
    select,
    table,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert

from ecommerce.infrastructure.repository import SQLAlchemyRepository
from ecommerce.modules.cart.models import Cart, CartItem

# Bare tables, so this module does not import the products module.
variants = table(
    "product_variants",
    column("id", Uuid),
    column("product_id", Uuid),
    column("sku", String),
    column("price", Integer),
    column("stock", Integer),
    column("options", JSONB),
)
products = table(
    "products", column("id", Uuid), column("name", String), column("is_active", Boolean)
)


class Stock(NamedTuple):
    stock: int
    is_active: bool


class CartRepository(SQLAlchemyRepository[Cart]):
    model = Cart

    async def find(self, user_id: UUID) -> UUID | None:
        return await self.session.scalar(select(Cart.id).where(Cart.user_id == user_id))

    async def ensure(self, user_id: UUID) -> UUID:
        # The no-op update makes RETURNING yield the existing row on conflict.
        new = insert(Cart).values(id=uuid7(), user_id=user_id)
        stmt = new.on_conflict_do_update(
            index_elements=["user_id"], set_={"user_id": new.excluded.user_id}
        ).returning(Cart.id)
        return (await self.session.execute(stmt)).scalar_one()

    async def variant(self, variant_id: UUID) -> Stock | None:
        stmt = (
            select(variants.c.stock, products.c.is_active)
            .join(products, products.c.id == variants.c.product_id)
            .where(variants.c.id == variant_id)
        )
        row = (await self.session.execute(stmt)).one_or_none()
        return Stock(row.stock, row.is_active) if row else None

    async def add_quantity(self, cart_id: UUID, variant_id: UUID, quantity: int) -> int:
        new = insert(CartItem).values(
            id=uuid7(), cart_id=cart_id, variant_id=variant_id, quantity=quantity
        )
        stmt = new.on_conflict_do_update(
            index_elements=["cart_id", "variant_id"],
            # The mixin's onupdate does not apply to ON CONFLICT DO UPDATE.
            set_={
                "quantity": CartItem.quantity + new.excluded.quantity,
                "updated_at": func.now(),
            },
        ).returning(CartItem.quantity)
        return (await self.session.execute(stmt)).scalar_one()

    async def set_quantity(self, cart_id: UUID, variant_id: UUID, quantity: int) -> bool:
        stmt = (
            update(CartItem)
            .where(CartItem.cart_id == cart_id, CartItem.variant_id == variant_id)
            .values(quantity=quantity)
            .returning(CartItem.id)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def remove(self, cart_id: UUID, variant_id: UUID) -> None:
        await self.session.execute(
            delete(CartItem).where(
                CartItem.cart_id == cart_id, CartItem.variant_id == variant_id
            )
        )

    async def clear(self, cart_id: UUID) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))

    async def lines(self, cart_id: UUID) -> list[Row[Any]]:
        stmt = (
            select(
                CartItem.variant_id,
                variants.c.product_id,
                products.c.name,
                variants.c.sku,
                variants.c.options,
                variants.c.price.label("unit_price"),
                CartItem.quantity,
                variants.c.stock,
                products.c.is_active,
            )
            .join(variants, variants.c.id == CartItem.variant_id)
            .join(products, products.c.id == variants.c.product_id)
            .where(CartItem.cart_id == cart_id)
            .order_by(CartItem.id)
        )
        return list((await self.session.execute(stmt)).all())
