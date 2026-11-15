from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.core.scratch import ScratchBase, WidgetRepository


@pytest.fixture(scope="session", autouse=True)
async def scratch_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(ScratchBase.metadata.create_all)


@pytest.fixture
async def session_factory(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Sessions commit into savepoints of one outer transaction rolled back at the end.
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield async_sessionmaker(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        await transaction.rollback()


@pytest.fixture
def widgets(db_session: AsyncSession) -> WidgetRepository:
    return WidgetRepository(db_session)
