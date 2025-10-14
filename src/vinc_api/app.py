import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .core.config import Settings, get_settings
from .core.logging import configure_logging
from .api.v1.router import router as api_v1_router
from .api.errors import register_exception_handlers
from .common.middleware import (
    JWTAuthMiddleware,
    TenantContextMiddleware,
    RequestIDMiddleware,
    DebugLoggingMiddleware,
)
from .core.db import init_engine
from .core.redis import init_redis, close_redis
from .core.mongo import init_mongo, close_mongo
from .core.tracing import init_tracing, instrument_fastapi
from .core.keycloak import init_keycloak


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    init_tracing(settings)

    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
    )

    # Middlewares (order matters: first added = outermost = runs first/last)
    # Debug logging should be the outermost middleware to capture everything
    app.add_middleware(DebugLoggingMiddleware, settings=settings)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(GZipMiddleware)
    app.add_middleware(JWTAuthMiddleware, settings=settings)
    app.add_middleware(TenantContextMiddleware, header_name=settings.TENANT_HEADER)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # Routers (versioned)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    instrument_fastapi(app, settings)

    # Lifespan: initialize and close shared clients
    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - runtime
        init_engine(settings=settings)
        init_redis(settings=settings)
        init_mongo(settings=settings)
        try:
            init_keycloak(settings=settings)
        except Exception:  # pragma: no cover - startup guard
            logger.exception("Failed to initialise Keycloak admin client")

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - runtime
        await close_redis()
        close_mongo()

    return app
