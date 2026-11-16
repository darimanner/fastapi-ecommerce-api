from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession


class SQLAlchemyUnitOfWork:
    """One session per `async with` block; subclasses attach repositories to it."""

    session: AsyncSession

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self._init_repositories()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # close() rolls back whatever was not committed explicitly.
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    def _init_repositories(self) -> None:
        """Create the repositories bound to `self.session`."""
