"""Retention survives SQL that bypasses the ORM."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.audit import AuditLog
from app.services import audit_service


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM audit_log",
        "UPDATE audit_log SET action='tampered'",
    ],
)
async def test_audit_records_cannot_be_rewritten_with_sql(db_session, statement):
    await audit_service.log_action(db_session, user_id=1, action="original", entity_type="user")
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text(statement))
    assert list(await db_session.scalars(select(AuditLog.action))) == ["original"]
