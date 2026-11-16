from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_ecommerce_api.api import health
from fastapi_ecommerce_api.config.settings import settings
from fastapi_ecommerce_api.core.db.sessions import engine
from fastapi_ecommerce_api.core.exceptions.handlers import register_exception_handlers
from fastapi_ecommerce_api.core.observability.logging import setup_logging
from fastapi_ecommerce_api.core.observability.middleware import request_context
from fastapi_ecommerce_api.modules.brands import router as brands
from fastapi_ecommerce_api.modules.categories import router as categories


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    setup_logging(settings.logger.level, debug=settings.logger.debug)
    app = FastAPI(title=settings.app.name, lifespan=lifespan)
    app.middleware("http")(request_context)
    register_exception_handlers(app)
    app.include_router(health.router)
    routers = (
        brands.router,
        brands.admin_router,
        categories.router,
        categories.admin_router,
    )
    for router in routers:
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
