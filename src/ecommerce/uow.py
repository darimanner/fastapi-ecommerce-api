from typing import Annotated

from fastapi import Depends

from ecommerce.core.db.sessions import session_factory
from ecommerce.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from ecommerce.modules.brands.repository import BrandRepository
from ecommerce.modules.categories.repository import CategoryRepository
from ecommerce.modules.products.repository import ProductRepository, VariantRepository


class AppUnitOfWork(SQLAlchemyUnitOfWork):
    """The one place that knows every module's repository (composition root)."""

    brands: BrandRepository
    categories: CategoryRepository
    products: ProductRepository
    variants: VariantRepository

    def _init_repositories(self) -> None:
        self.brands = BrandRepository(self.session)
        self.categories = CategoryRepository(self.session)
        self.products = ProductRepository(self.session)
        self.variants = VariantRepository(self.session)


def get_uow() -> AppUnitOfWork:
    return AppUnitOfWork(session_factory)


UoW = Annotated[AppUnitOfWork, Depends(get_uow)]
