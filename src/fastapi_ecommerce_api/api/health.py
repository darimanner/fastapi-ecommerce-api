import asyncio

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from fastapi_ecommerce_api.core.db.sessions import DbSession
from fastapi_ecommerce_api.core.exceptions.base import ServiceUnavailableError

router = APIRouter(prefix="/health", include_in_schema=False)


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: DbSession) -> dict[str, str]:
    try:
        async with asyncio.timeout(2):
            await db.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError) as exc:
        raise ServiceUnavailableError("Database is unreachable") from exc
    return {"status": "ok"}
