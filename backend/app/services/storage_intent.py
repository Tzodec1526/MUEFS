"""Track storage keys written inside a request so commit failure can reclaim them."""

from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.services import document_service

logger = logging.getLogger(__name__)

_PENDING = "pending_storage_keys"


def track_upload(session: Session, file_key: str) -> None:
    session.info.setdefault(_PENDING, set()).add(file_key)


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


@event.listens_for(Session, "after_commit")
def _clear_pending_uploads(session: Session) -> None:
    session.info.pop(_PENDING, None)
