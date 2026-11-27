from typing import Annotated

from fastapi import Depends

from ecommerce.core.db.sessions import session_factory
from ecommerce.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from ecommerce.modules.auth.repository import UserRepository
from ecommerce.modules.brands.repository import BrandRepository
from ecommerce.modules.cart.repository import CartRepository
from ecommerce.modules.categories.repository import CategoryRepository
from ecommerce.modules.products.repository import ProductRepository, VariantRepository


class AppUnitOfWork(SQLAlchemyUnitOfWork):
    """The one place that knows every module's repository (composition root)."""

    brands: BrandRepository
    carts: CartRepository
    categories: CategoryRepository
    products: ProductRepository
    users: UserRepository
    variants: VariantRepository

    def _init_repositories(self) -> None:
        self.users = UserRepository(self.session)
        self.brands = BrandRepository(self.session)
        self.carts = CartRepository(self.session)
        self.categories = CategoryRepository(self.session)
        self.products = ProductRepository(self.session)
        self.variants = VariantRepository(self.session)


def get_uow() -> AppUnitOfWork:
    return AppUnitOfWork(session_factory)


UoW = Annotated[AppUnitOfWork, Depends(get_uow)]
