from uuid import UUID

from ecommerce.core.exceptions.base import ConflictError


class CategoryCycleError(ConflictError):
    def __init__(self, category_id: UUID, parent_id: UUID) -> None:
        super().__init__(
            f"Category {category_id} cannot move under itself or its descendant "
            f"{parent_id}",
            category_id=str(category_id),
            parent_id=str(parent_id),
        )


class CategoryDepthError(ConflictError):
    def __init__(self, category_id: UUID | None, parent_id: UUID, max_depth: int) -> None:
        super().__init__(
            f"Placing the category under {parent_id} exceeds the maximum depth "
            f"of {max_depth}",
            category_id=category_id and str(category_id),
            parent_id=str(parent_id),
            max_depth=max_depth,
        )
