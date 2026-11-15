from uuid import UUID

from sqlalchemy import func, literal, select

from fastapi_ecommerce_api.infrastructure.repository import SQLAlchemyRepository
from fastapi_ecommerce_api.modules.categories.models import Category

TREE_LOCK_KEY = 0x6361745F74726565  # "cat_tree"


class CategoryRepository(SQLAlchemyRepository[Category]):
    model = Category

    async def lock_tree(self) -> None:
        """Serialize tree moves until commit: two checks cannot pass on stale reads."""
        await self.session.execute(select(func.pg_advisory_xact_lock(TREE_LOCK_KEY)))

    async def path_to_root(self, category_id: UUID) -> list[UUID]:
        """Ids from `category_id` up to its root, inclusive; empty if it is missing."""
        up = (
            select(Category.id, Category.parent_id)
            .where(Category.id == category_id)
            .cte("up", recursive=True)
        )
        # UNION, not UNION ALL: it drops repeated rows, so the walk ends even on a cycle.
        up = up.union(
            select(Category.id, Category.parent_id).join(
                up, Category.id == up.c.parent_id
            )
        )
        return list(await self.session.scalars(select(up.c.id)))

    async def subtree_height(self, category_id: UUID) -> int:
        """Levels in the subtree rooted at `category_id`; a leaf is 1."""
        down = (
            select(Category.id, literal(1).label("level"))
            .where(Category.id == category_id)
            .cte("down", recursive=True)
        )
        down = down.union_all(
            select(Category.id, down.c.level + 1).join(
                down, Category.parent_id == down.c.id
            )
        )
        return await self.session.scalar(select(func.max(down.c.level))) or 0
