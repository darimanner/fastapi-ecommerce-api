from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Slice[T]:
    """One page of rows; `has_next` comes from fetching one extra row, not count(*)."""

    items: list[T]
    has_next: bool


class Repository[T](Protocol):
    async def get(self, entity_id: UUID) -> T | None: ...

    async def add(self, entity: T) -> T: ...

    async def add_many(self, rows: Sequence[Mapping[str, object]]) -> list[T]: ...

    async def update(self, entity: T, values: Mapping[str, object]) -> T: ...

    async def delete(self, entity: T) -> None: ...

    async def list_offset(self, limit: int, offset: int) -> Slice[T]: ...

    async def list_after(self, after: UUID | None, limit: int) -> Slice[T]: ...
