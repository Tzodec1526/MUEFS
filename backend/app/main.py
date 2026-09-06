import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import database
from app.api.router import api_router
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware, close_rate_limit_redis
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.readiness import router as readiness_router
from app.security.startup import validate_security_config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    validate_security_config()
    try:
        yield
    finally:
        await close_rate_limit_redis()
        await getattr(app.state, "readiness_engine", database.engine).dispose()


app = FastAPI(
    title="Michigan Unified E-Filing System",
    description="Statewide unified e-filing platform for Michigan courts",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Demo-User-Id",
        "X-Demo-Auth-Secret",
        "Idempotency-Key",
    ],
)
app.add_middleware(RateLimitMiddleware)


app.include_router(api_router, prefix="/api/v1")
app.include_router(readiness_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions — log details server-side, return generic message to client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        content={"status": "healthy", "service": "muefs-api"},
        headers={"Cache-Control": "no-store"},
    )
