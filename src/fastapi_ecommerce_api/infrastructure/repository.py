from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import Select, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_ecommerce_api.core.db.mixins.uuid_pk import UUIDPrimaryKeyMixin
from fastapi_ecommerce_api.interfaces.repository import Slice


class SQLAlchemyRepository[ModelT: UUIDPrimaryKeyMixin]:
    """Generic CRUD over one model; writes flush, so constraint errors raise here."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_many(self, rows: Sequence[Mapping[str, object]]) -> list[ModelT]:
        if not rows:
            return []
        result = await self.session.scalars(
            insert(self.model).returning(self.model), list(rows)
        )
        return list(result.all())

    async def update(self, entity: ModelT, values: Mapping[str, object]) -> ModelT:
        for field, value in values.items():
            setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def list_offset(self, limit: int, offset: int) -> Slice[ModelT]:
        stmt = select(self.model).order_by(self.model.id).offset(offset)
        return await self._slice(stmt, limit)

    async def list_after(self, after: UUID | None, limit: int) -> Slice[ModelT]:
        stmt = select(self.model).order_by(self.model.id)
        if after is not None:
            stmt = stmt.where(self.model.id > after)
        return await self._slice(stmt, limit)

    async def _slice(self, stmt: Select[ModelT], limit: int) -> Slice[ModelT]:
        rows = list((await self.session.scalars(stmt.limit(limit + 1))).all())
        return Slice(rows[:limit], has_next=len(rows) > limit)
