"""Delete committed, unreferenced draft objects; --once drains the currently due queue."""

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import async_session, engine
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument
from app.models.storage_deletion import StorageDeletion
from app.services import audit_service, document_service

logger = logging.getLogger(__name__)


async def cleanup_next(
    sessions: async_sessionmaker[AsyncSession],
) -> Literal["deleted", "retry"] | None:
    async with sessions.begin() as db:
        # SQLite ignores FOR UPDATE; reserve its writer before selecting a job.
        if db.get_bind().dialect.name == "sqlite":
            await db.execute(text("BEGIN IMMEDIATE"))
        job = await db.scalar(
            select(StorageDeletion)
            .where(StorageDeletion.next_attempt_at <= datetime.now(UTC))
            .order_by(StorageDeletion.next_attempt_at, StorageDeletion.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        referenced = await db.scalar(select(or_(
            select(FilingDocument.id).where(FilingDocument.file_key == job.file_key).exists(),
            select(DocumentPublicCopy.id)
            .where(DocumentPublicCopy.file_key == job.file_key).exists(),
        )))
        error = None
        if referenced:
            error = "Object is still referenced by a filing document or public copy"
        else:
            try:
                await asyncio.to_thread(document_service.delete_document, job.file_key)
            except Exception as exc:
                # SDK errors may contain storage credentials or private object URLs.
                error = f"Storage deletion failed ({type(exc).__name__})"
        if error is not None:
            job.attempt_count += 1
            job.last_error = error
            job.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(3600, 30 * 2 ** min(job.attempt_count - 1, 7)),
            )
            logger.warning("Storage deletion %s deferred: %s", job.id, error)
            return "retry"

        await audit_service.log_action(
            db, user_id=None, action="purge_draft_document", entity_type="filing_document",
            entity_id=job.document_id,
            details={"filing_id": job.envelope_id, "file_key": job.file_key,
                     "deletion_id": job.id, "queued_at": job.queued_at.isoformat()},
        )
        await db.delete(job)
        # If this commit fails or the process stops, a repeat deletion is safe.
        return "deleted"


async def drain(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Delete every object that is due now, for deployments that run no worker."""
    while await cleanup_next(sessions) == "deleted":
        pass


async def run(once: bool = False) -> int:
    if settings.demo_isolated_sessions:
        raise RuntimeError("Storage cleanup cannot operate on isolated demo databases")
    failed = False
    try:
        while True:
            try:
                result = await cleanup_next(async_session)
                if result == "retry":
                    failed = True
                elif result is None:
                    if once:
                        return int(failed)
                    await asyncio.sleep(5)
            except Exception:
                failed = True
                logger.exception("Storage cleanup iteration failed")
                if once:
                    return 1
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Delete committed, unreferenced draft objects; --once drains the currently "
            "due queue."
        ),
    )
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(run(once=parser.parse_args().once)))
