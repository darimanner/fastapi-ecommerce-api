from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ecommerce.infrastructure.repository import SQLAlchemyRepository
from ecommerce.modules.products.models import Product, ProductVariant


class ProductRepository(SQLAlchemyRepository[Product]):
    model = Product

    async def get_active(self, product_id: UUID) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.id == product_id, Product.is_active)
            .options(selectinload(Product.variants))
        )
        return await self.session.scalar(stmt)


class VariantRepository(SQLAlchemyRepository[ProductVariant]):
    model = ProductVariant
