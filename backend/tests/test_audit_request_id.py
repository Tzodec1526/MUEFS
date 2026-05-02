"""Audit entries pick up the active request id from the contextvar."""

import pytest

from app.logging_config import set_request_id
from app.services import audit_service


@pytest.mark.asyncio
async def test_audit_log_records_request_id_when_set(db_session):
    set_request_id("rid-test-123")
    try:
        entry = await audit_service.log_action(
            db_session, user_id=1, action="probe-rid", entity_type="test",
        )
    finally:
        set_request_id(None)
    assert entry.details is not None
    assert entry.details.get("request_id") == "rid-test-123"


@pytest.mark.asyncio
async def test_audit_log_omits_request_id_when_unset(db_session):
    set_request_id(None)
    entry = await audit_service.log_action(
        db_session, user_id=1, action="probe-no-rid", entity_type="test",
    )
    # No request id in scope: details stays whatever the caller passed (None here).
    assert entry.details is None


@pytest.mark.asyncio
async def test_audit_log_preserves_caller_details(db_session):
    set_request_id("rid-merge")
    try:
        entry = await audit_service.log_action(
            db_session,
            user_id=1,
            action="probe-merge",
            entity_type="test",
            details={"foo": "bar"},
        )
    finally:
        set_request_id(None)
    assert entry.details == {"foo": "bar", "request_id": "rid-merge"}
