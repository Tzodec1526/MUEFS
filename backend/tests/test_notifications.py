"""Notification API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.notification import DeliveryStatus, Notification, NotificationType
from app.models.user import User, UserType


@pytest.mark.asyncio
async def test_notification_summary_counts_unread(db_session):
    user = User(
        email="notify@example.com",
        first_name="Notify",
        last_name="User",
        user_type=UserType.ATTORNEY,
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add_all(
        [
            Notification(
                notification_type=NotificationType.CASE_UPDATE,
                recipient_id=user.id,
                subject="Update",
                body="Body",
                delivery_status=DeliveryStatus.SENT,
            ),
            Notification(
                notification_type=NotificationType.FILING_ACCEPTED,
                recipient_id=user.id,
                subject="Accepted",
                body="Body",
                delivery_status=DeliveryStatus.DELIVERED,
            ),
        ]
    )
    await db_session.commit()

    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Demo-User-Id": str(user.id)},
        ) as client:
            summary = await client.get("/api/v1/notifications/summary")
            listing = await client.get("/api/v1/notifications")
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    assert summary.json()["total"] == 2
    assert summary.json()["unread"] == 1

    assert listing.status_code == 200
    assert listing.json()["unread"] == 1
    assert len(listing.json()["notifications"]) == 2
