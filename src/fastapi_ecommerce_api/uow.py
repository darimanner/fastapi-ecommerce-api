from typing import Annotated

from fastapi import Depends

from fastapi_ecommerce_api.core.db.sessions import session_factory
from fastapi_ecommerce_api.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from fastapi_ecommerce_api.modules.brands.repository import BrandRepository
from fastapi_ecommerce_api.modules.categories.repository import CategoryRepository


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
