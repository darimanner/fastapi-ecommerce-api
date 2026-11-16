import os

# Settings are read at import time; tests override get_db, so this URL is never used.
os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://test:test@localhost/test")

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from ecommerce.core.db.sessions import get_db
from ecommerce.main import app
from ecommerce.uow import AppUnitOfWork, get_uow


def migrate(connection: Connection) -> None:
    config = Config(toml_file=Path(__file__).parents[1] / "pyproject.toml")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    command.check(config)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(migrate)
    yield engine
    await engine.dispose()


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
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_uow] = lambda: AppUnitOfWork(session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
