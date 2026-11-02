import asyncio
import logging
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app import database

logger = logging.getLogger(__name__)
router = APIRouter()
EXPECTED_HEADS = frozenset(
    ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic")).get_heads(),
)
TIMEOUT_SECONDS = 3


@router.get("/ready", include_in_schema=False)
async def readiness(request: Request) -> JSONResponse:
    engine = getattr(request.app.state, "readiness_engine", database.engine)
    reason = None
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS), engine.connect() as connection:
            current = await connection.run_sync(
                lambda conn: MigrationContext.configure(conn).get_current_heads(),
            )
            if not EXPECTED_HEADS or frozenset(current) != EXPECTED_HEADS:
                reason = "schema_mismatch"
    except TimeoutError:
        reason = "database_timeout"
    except Exception as exc:
        logger.warning("Readiness database check failed (%s)", type(exc).__name__)
        reason = "database_unavailable"
    if reason:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "muefs-api", "reason": reason},
            headers={"Cache-Control": "no-store", "Retry-After": "5"},
        )
    return JSONResponse(
        content={"status": "ready", "service": "muefs-api"},
        headers={"Cache-Control": "no-store"},
    )
