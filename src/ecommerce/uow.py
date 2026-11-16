from typing import Annotated

from fastapi import Depends

from ecommerce.core.db.sessions import session_factory
from ecommerce.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from ecommerce.modules.brands.repository import BrandRepository
from ecommerce.modules.categories.repository import CategoryRepository


class AppUnitOfWork(SQLAlchemyUnitOfWork):
    """The one place that knows every module's repository (composition root)."""

    brands: BrandRepository
    categories: CategoryRepository

    def _init_repositories(self) -> None:
        self.brands = BrandRepository(self.session)
        self.categories = CategoryRepository(self.session)


def get_uow() -> AppUnitOfWork:
    return AppUnitOfWork(session_factory)


UoW = Annotated[AppUnitOfWork, Depends(get_uow)]
