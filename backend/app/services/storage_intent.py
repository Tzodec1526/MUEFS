from __future__ import annotations

import logging

import anyio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.services import document_service

logger = logging.getLogger(__name__)

_PENDING = "pending_storage_keys"
_DELETIONS = "queued_storage_deletions"


def track_upload(session: Session, file_key: str) -> None:
    session.info.setdefault(_PENDING, set()).add(file_key)


def track_deletion(session: Session) -> None:
    session.info[_DELETIONS] = True


def queued_deletion(session: Session) -> bool:
    return bool(session.info.get(_DELETIONS))


def release_upload(session: Session, file_key: str) -> None:
    pending = session.info.get(_PENDING)
    if pending is not None:
        pending.discard(file_key)


def take_pending_uploads(session: Session) -> set[str]:
    return set(session.info.pop(_PENDING, set()) or ())


def purge_keys(file_keys: set[str]) -> None:
    for file_key in file_keys:
        try:
            document_service.delete_document(file_key)
        except Exception:
            logger.warning("Failed to reclaim rolled-back upload %s", file_key, exc_info=True)


async def _referenced(sessions: async_sessionmaker[AsyncSession], keys: set[str]) -> set[str]:
    from app.models.document_public_copy import DocumentPublicCopy
    from app.models.filing import FilingDocument

    try:
        async with sessions() as check:
            found = set(await check.scalars(
                select(FilingDocument.file_key).where(FilingDocument.file_key.in_(keys))
            ))
            found |= set(await check.scalars(
                select(DocumentPublicCopy.file_key).where(DocumentPublicCopy.file_key.in_(keys))
            ))
    except Exception:
        logger.warning("Could not confirm a failed commit; retaining %d uploads", len(keys),
                       exc_info=True)
        return set(keys)
    return found


async def rollback_with_upload_cleanup(
    session: AsyncSession, *, verify_with: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    pending = take_pending_uploads(session.sync_session)
    with anyio.CancelScope(shield=True):
        try:
            await session.rollback()
        finally:
            if pending and verify_with is not None:
                pending -= await _referenced(verify_with, pending)
            if pending:
                await anyio.to_thread.run_sync(purge_keys, pending)


@event.listens_for(Session, "after_commit")
def _clear_pending_uploads(session: Session) -> None:
    if session.in_nested_transaction():
        return
    session.info.pop(_PENDING, None)
