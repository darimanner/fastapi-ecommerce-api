from typing import Any, Protocol
from uuid import UUID

from fastapi_ecommerce_api.core.crud import CRUDService
from fastapi_ecommerce_api.interfaces.repository import Repository
from fastapi_ecommerce_api.interfaces.unit_of_work import UnitOfWork
from fastapi_ecommerce_api.modules.categories.exceptions import (
    CategoryCycleError,
    CategoryDepthError,
)
from fastapi_ecommerce_api.modules.categories.models import Category
from fastapi_ecommerce_api.modules.categories.schemas import (
    CategoryCreate,
    CategoryUpdate,
)


class CategoryTree(Repository[Category], Protocol):
    async def lock_tree(self) -> None: ...

    async def refresh_parent(self, category: Category) -> None: ...

    async def path_to_root(self, category_id: UUID) -> list[UUID]: ...

    async def subtree_height(self, category_id: UUID) -> int: ...


class CategoryUnitOfWork(UnitOfWork, Protocol):
    # Read-only, so the app UoW may declare the concrete repository type.
    @property
    def categories(self) -> CategoryTree: ...


class CategoryService(CRUDService[Category, CategoryCreate, CategoryUpdate]):
    def __init__(self, uow: CategoryUnitOfWork, max_depth: int) -> None:
        super().__init__(uow, lambda: uow.categories)
        self._tree_uow = uow
        self._max_depth = max_depth

    async def _before_write(
        self, entity: Category | None, values: dict[str, Any]
    ) -> None:
        parent_id = values.get("parent_id")
        if "parent_id" not in values or (entity is None and parent_id is None):
            return
        categories = self._tree_uow.categories
        await categories.lock_tree()
        if entity is not None:
            # The entity was read before the lock; compare with the committed parent.
            await categories.refresh_parent(entity)
            if entity.parent_id == parent_id:
                return
        if parent_id is not None:
            await self._check_move(categories, entity, parent_id)

    async def _check_move(
        self, categories: CategoryTree, entity: Category | None, parent_id: UUID
    ) -> None:
        path = await categories.path_to_root(parent_id)
        if entity is not None and entity.id in path:
            raise CategoryCycleError(entity.id, parent_id)
        height = await categories.subtree_height(entity.id) if entity else 1
        # An empty path means the parent is missing: the foreign key answers 422.
        if path and len(path) + height > self._max_depth:
            category_id = entity.id if entity else None
            raise CategoryDepthError(category_id, parent_id, self._max_depth)
