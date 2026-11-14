import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.core.scratch import ScratchBase, WidgetRepository


@pytest.fixture(scope="session", autouse=True)
async def scratch_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(ScratchBase.metadata.create_all)


@pytest.fixture
def widgets(db_session: AsyncSession) -> WidgetRepository:
    return WidgetRepository(db_session)
