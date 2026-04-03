import logging
import time
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Michigan Unified E-Filing System",
    description="Statewide unified e-filing platform for Michigan courts",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Demo-User-Id"],
)


# Simple in-memory rate limiter (use Redis-backed in production)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_last_cleanup = 0.0
RATE_LIMIT_REQUESTS = 60  # per window
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_IPS = 10000  # Prevent unbounded memory growth


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Basic rate limiting per IP address."""
    global _rate_limit_last_cleanup
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Periodic cleanup of stale IPs (every 5 minutes)
    if now - _rate_limit_last_cleanup > 300:
        stale_ips = [
            ip for ip, ts in _rate_limit_store.items()
            if not ts or now - ts[-1] > RATE_LIMIT_WINDOW
        ]
        for ip in stale_ips:
            del _rate_limit_store[ip]
        _rate_limit_last_cleanup = now

    # Clean old entries for this IP
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return Response(
            content='{"detail":"Rate limit exceeded. Try again later."}',
            status_code=429,
            media_type="application/json",
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions — log details server-side, return generic message to client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "muefs-api"}
