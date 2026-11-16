from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    Uuid,
    column,
    desc,
    func,
    select,
    table,
    tuple_,
)
from sqlalchemy.orm import selectinload

from ecommerce.infrastructure.repository import SQLAlchemyRepository
from ecommerce.interfaces.repository import Slice
from ecommerce.modules.products.models import Product, ProductVariant
from ecommerce.modules.products.schemas import ProductQuery

# A bare table, so this module does not import the categories module.
categories = table("categories", column("id", Uuid), column("parent_id", Uuid))


class ProductRepository(SQLAlchemyRepository[Product]):
    model = Product

    async def get_active(self, product_id: UUID) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.id == product_id, Product.is_active)
            .options(selectinload(Product.variants))
        )
        return await self.session.scalar(stmt)

    async def list_public(self, query: ProductQuery) -> Slice[Row[Any]]:
        stmt = _public(query)
        after = query.after()
        if query.sort == "newest":
            # UUIDv7 ids grow with creation time.
            stmt = stmt.order_by(Product.id.desc())
            if after:
                stmt = stmt.where(Product.id < after.id)
        else:
            key = tuple_(stmt.selected_columns.price, Product.id)
            ascending = query.sort == "price_asc"
            stmt = stmt.order_by(*(key.clauses if ascending else map(desc, key.clauses)))
            if after:
                position = tuple_(*after)
                stmt = stmt.where(key > position if ascending else key < position)
        rows = list((await self.session.execute(stmt.limit(query.limit + 1))).all())
        return Slice(rows[: query.limit], has_next=len(rows) > query.limit)

    async def count_public(self, query: ProductQuery) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(_public(query).subquery())
            )
            or 0
        )


class VariantRepository(SQLAlchemyRepository[ProductVariant]):
    model = ProductVariant


def _public(query: ProductQuery) -> Select[Any]:
    """Active products with a matching variant, priced at the cheapest one."""
    prices = select(
        ProductVariant.product_id, func.min(ProductVariant.price).label("price")
    ).group_by(ProductVariant.product_id)
    if query.options:
        prices = prices.where(ProductVariant.options.contains(query.options))
    lowest = prices.subquery()
    conditions: list[ColumnElement[bool]] = [Product.is_active.is_(True)]
    if query.brand_id is not None:
        conditions.append(Product.brand_id == query.brand_id)
    if query.category_id is not None:
        conditions.append(Product.category_id.in_(_subtree(query.category_id)))
    if query.min_price is not None:
        conditions.append(lowest.c.price >= query.min_price)
    if query.max_price is not None:
        conditions.append(lowest.c.price <= query.max_price)
    return (
        select(
            Product.id,
            Product.name,
            Product.slug,
            Product.brand_id,
            Product.category_id,
            lowest.c.price,
        )
        .join(lowest, lowest.c.product_id == Product.id)
        .where(*conditions)
    )


def _subtree(root: UUID) -> Select[tuple[UUID]]:
    down = (
        select(categories.c.id)
        .where(categories.c.id == root)
        .cte("subtree", recursive=True)
    )
    # UNION drops repeated rows, so the walk ends even on a cycle.
    down = down.union(
        select(categories.c.id).join(down, categories.c.parent_id == down.c.id)
    )
    return select(down.c.id)
