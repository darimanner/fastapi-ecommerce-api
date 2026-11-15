from typing import Any, Protocol

from fastapi_ecommerce_api.core.crud import CRUDService
from fastapi_ecommerce_api.interfaces.unit_of_work import UnitOfWork
from fastapi_ecommerce_api.modules.categories.exceptions import (
    CategoryCycleError,
    CategoryDepthError,
)
from fastapi_ecommerce_api.modules.categories.models import Category
from fastapi_ecommerce_api.modules.categories.repository import CategoryRepository
from fastapi_ecommerce_api.modules.categories.schemas import (
    CategoryCreate,
    CategoryUpdate,
)


class CategoryUnitOfWork(UnitOfWork, Protocol):
    categories: CategoryRepository


class CategoryService(CRUDService[Category, CategoryCreate, CategoryUpdate]):
    def __init__(self, uow: CategoryUnitOfWork, max_depth: int) -> None:
        super().__init__(uow, lambda: uow.categories)
        self._tree_uow = uow
        self._max_depth = max_depth

    async def _before_write(
        self, entity: Category | None, values: dict[str, Any]
    ) -> None:
        parent_id = values.get("parent_id")
        if parent_id is None or (entity is not None and entity.parent_id == parent_id):
            return
        categories = self._tree_uow.categories
        await categories.lock_tree()
        path = await categories.path_to_root(parent_id)
        if entity is not None and entity.id in path:
            raise CategoryCycleError(entity.id, parent_id)
        height = await categories.subtree_height(entity.id) if entity else 1
        # A missing parent gives an empty path; the foreign key then answers 422.
        if len(path) + height > self._max_depth:
            raise CategoryDepthError(parent_id, self._max_depth)
