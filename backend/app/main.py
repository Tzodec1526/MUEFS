import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DataError, DBAPIError

from app import database
from app.api.router import api_router
from app.config import settings
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, close_rate_limit_redis
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.readiness import router as readiness_router
from app.security.startup import validate_security_config
from app.services.document_service import StorageQuotaExceededError, StorageUnavailableError

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

# The last middleware added runs first. CORS and security headers must wrap the
# limiters so a 413 or 429 is readable by the browser, and preflights are never counted.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
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


@app.exception_handler(StorageUnavailableError)
async def storage_unavailable_handler(request: Request, exc: Exception):
    """A storage outage is retryable; it must not look like a missing record or a crash."""
    logger.error("Document storage failed on %s %s", request.method, request.url.path,
                 exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Document storage is temporarily unavailable. Please retry shortly."},
        headers={"Retry-After": "30"},
    )


@app.exception_handler(StorageQuotaExceededError)
async def storage_quota_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=507, content={"detail": str(exc)})


@app.exception_handler(OverflowError)
async def out_of_range_handler(request: Request, exc: Exception):
    """Date arithmetic on values at the edge of the calendar overflows; that is bad input."""
    logger.warning("Out-of-range value on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=422,
        content={"detail": "A date or number in the request is outside the supported range."},
    )


@app.exception_handler(DBAPIError)
async def database_error_handler(request: Request, exc: Exception):
    """PostgreSQL rejects some text and numbers the request validation allows, such as
    NUL characters. SQLSTATE class 22 (data exception) means the input was invalid."""
    sqlstate = str(getattr(getattr(exc, "orig", None), "sqlstate", None) or "")
    if not isinstance(exc, DataError) and not sqlstate.startswith("22"):
        raise exc
    logger.warning("Rejected invalid data on %s %s (SQLSTATE %s)",
                   request.method, request.url.path, sqlstate or "unknown")
    return JSONResponse(
        status_code=422, content={"detail": "The request contains a value that cannot be stored."},
    )


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        content={"status": "healthy", "service": "muefs-api"},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/config.js", include_in_schema=False)
async def runtime_frontend_config() -> Response:
    """Supply local and hosted demos with the same uncached browser configuration.

    Only isolated public sandboxes publish the demo token here. A shared-database
    deployment must not give every visitor a header that impersonates any account.
    """
    publish = settings.allow_demo_mode and settings.demo_isolated_sessions
    secret = settings.demo_mode_secret if publish else ""
    return Response(
        content=f"window.__MUEFS_DEMO_SECRET__={json.dumps(secret)};",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )
