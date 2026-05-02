from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.config import settings
from app.database import get_db
from app.logging_config import configure_logging, get_logger
from app.middleware import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    close_rate_limit_redis,
)

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await close_rate_limit_redis()


app = FastAPI(
    title="Michigan Unified E-Filing System",
    description="Statewide unified e-filing platform for Michigan courts",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware order: outer to inner. RequestId runs first so other layers + handlers
# see request.state.request_id; SecurityHeaders runs last so its headers are not
# overwritten by anything downstream.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Demo-User-Id", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions — log details server-side, return generic message to client."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unhandled error on %s %s (request_id=%s)",
        request.method,
        request.url.path,
        request_id,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe: the process is up and the event loop is responsive.

    Use ``/health/ready`` to also verify downstream dependencies before sending traffic.
    """
    return {"status": "healthy", "service": "muefs-api"}


@app.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness probe: confirms the database is reachable.

    Returns 200 with ``{"status": "ready", ...}`` when ``SELECT 1`` succeeds and 503 with
    ``{"status": "unready", "reason": ...}`` otherwise so a load balancer can route around
    a half-booted pod.
    """
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Readiness probe: database unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "unready", "reason": "database", "checks": checks},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "service": "muefs-api", "checks": checks},
    )
