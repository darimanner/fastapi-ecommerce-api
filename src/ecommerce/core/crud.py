from collections.abc import Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ecommerce.core.exceptions.base import NotFoundError
from ecommerce.core.pagination.offset import OffsetParams
from ecommerce.interfaces.repository import Repository, Slice
from ecommerce.interfaces.unit_of_work import UnitOfWork


class CRUDService[ModelT, CreateT: BaseModel, UpdateT: BaseModel]:
    """Standard CRUD, one transaction per call; domain rules go in `_before_write`."""

    def __init__(
        self, uow: UnitOfWork, repository: Callable[[], Repository[ModelT]]
    ) -> None:
        self._uow = uow
        # A getter, because repositories exist only inside `async with uow`.
        self._repository = repository

    async def get(self, entity_id: UUID) -> ModelT:
        async with self._uow:
            return await self._get(entity_id)

    async def list_offset(self, params: OffsetParams) -> Slice[ModelT]:
        async with self._uow:
            return await self._repository().list_offset(params.limit, params.offset)

    async def create(self, data: CreateT) -> ModelT:
        values = data.model_dump()
        async with self._uow:
            await self._before_write(None, values)
            repository = self._repository()
            entity = await repository.add(repository.model(**values))
            await self._uow.commit()
        await self._after_write()
        return entity

    async def replace(self, entity_id: UUID, data: CreateT) -> ModelT:
        return await self._write(entity_id, data.model_dump())

    async def update(self, entity_id: UUID, data: UpdateT) -> ModelT:
        return await self._write(entity_id, data.model_dump(exclude_unset=True))

    async def delete(self, entity_id: UUID) -> None:
        async with self._uow:
            await self._repository().delete(await self._get(entity_id))
            await self._uow.commit()
        await self._after_write()

    async def _before_write(self, entity: ModelT | None, values: dict[str, Any]) -> None:
        """Runs inside the write transaction; `entity` is None on create."""

    async def _after_write(self) -> None:
        """Runs after a successful commit, e.g. to invalidate caches."""

    async def _write(self, entity_id: UUID, values: dict[str, Any]) -> ModelT:
        async with self._uow:
            entity = await self._get(entity_id)
            await self._before_write(entity, values)
            await self._repository().update(entity, values)
            await self._uow.commit()
        await self._after_write()
        return entity

    async def _get(self, entity_id: UUID) -> ModelT:
        repository = self._repository()
        if (entity := await repository.get(entity_id)) is None:
            raise NotFoundError(f"{repository.model.__name__} {entity_id} not found")
        return entity
