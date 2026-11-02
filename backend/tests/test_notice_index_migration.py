from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.models.notification import DeliveryStatus, Notification, NotificationType
from app.models.user import User, UserType
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", ["f06c31a8b7d2"], indirect=True)
async def test_notice_index_upgrade_recovers_interruption_without_changing_messages(
    postgres_sessions,
):
    async with postgres_sessions.begin() as db:
        user = User(email="notice-index@example.com", first_name="Notice", last_name="Recipient",
                    user_type=UserType.ATTORNEY)
        db.add(user)
        await db.flush()
        notice = Notification(recipient_id=user.id, notification_type=NotificationType.CASE_UPDATE,
            subject="Synthetic pending notice", body="Retained body", email_message="Retained MIME",
            email_message_id="synthetic-index@example.com", attempt_count=2,
            next_attempt_at=datetime(2026, 1, 1, tzinfo=UTC),
            delivery_status=DeliveryStatus.PENDING)
        db.add(notice)
        await db.flush()
        notice_id = notice.id
    engine = postgres_sessions.kw["bind"]
    async with engine.connect() as db:
        await db.execution_options(isolation_level="AUTOCOMMIT")
        with pytest.raises(DBAPIError, match="invalid input syntax for type integer"):
            await db.execute(text("""CREATE INDEX CONCURRENTLY ix_notification_recipient_newest
                ON notifications ((subject::integer))"""))
        assert await db.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid='ix_notification_recipient_newest'::regclass""")) is False
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    for operation, target in [
        ("upgrade", "head"), ("downgrade", "f06c31a8b7d2"), ("upgrade", "head"),
    ]:
        async with engine.connect() as db:
            def migrate(connection):
                config.attributes["connection"] = connection
                getattr(command, operation)(config, target)
            await db.run_sync(migrate)
            indexes = await db.run_sync(lambda conn: inspect(conn).get_indexes("notifications"))
            by_name = {item["name"]: item["column_names"] for item in indexes}
            if operation == "upgrade":
                assert by_name["ix_notification_recipient_newest"] == [
                    "recipient_id", "created_at", "id",
                ]
                assert "ix_notifications_recipient_id" not in by_name
            else:
                assert by_name["ix_notifications_recipient_id"] == ["recipient_id"]
                assert "ix_notification_recipient_newest" not in by_name
            assert by_name["ix_notifications_filing_envelope_id"] == ["filing_envelope_id"]
        async with postgres_sessions() as db:
            current = (await db.scalars(select(Notification))).one()
            assert current.id == notice_id and current.email_message == "Retained MIME"
            assert current.body == "Retained body" and current.attempt_count == 2
            assert current.delivery_status == DeliveryStatus.PENDING
            assert current.next_attempt_at == datetime(2026, 1, 1, tzinfo=UTC)
