"""Audit log append-only enforcement."""

import pytest
from sqlalchemy.exc import InvalidRequestError

from app.models.audit import AuditLog
from app.services import audit_service


@pytest.mark.asyncio
async def test_audit_log_delete_blocked(db_session):
    entry = await audit_service.log_action(
        db_session, user_id=1, action="probe", entity_type="test",
    )
    await db_session.flush()
    await db_session.delete(entry)
    with pytest.raises(InvalidRequestError, match="append-only"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_audit_log_update_blocked(db_session):
    entry = await audit_service.log_action(
        db_session, user_id=1, action="probe2", entity_type="test",
    )
    await db_session.flush()
    row = await db_session.get(AuditLog, entry.id)
    assert row is not None
    row.action = "tampered"
    with pytest.raises(InvalidRequestError, match="append-only"):
        await db_session.flush()
