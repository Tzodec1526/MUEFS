from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import DeliveryStatus, Notification, NotificationType


async def create_notification(
    db: AsyncSession,
    *,
    notification_type: NotificationType,
    recipient_id: int,
    filing_envelope_id: int | None,
    subject: str,
    body: str,
) -> Notification:
    notification = Notification(
        notification_type=notification_type,
        recipient_id=recipient_id,
        filing_envelope_id=filing_envelope_id,
        subject=subject,
        body=body,
        delivery_status=DeliveryStatus.PENDING,
    )
    db.add(notification)
    await db.flush()
    return notification


async def notify_filing_status_change(
    db: AsyncSession,
    *,
    filer_id: int,
    filing_id: int,
    status: str,
    court_name: str,
    case_title: str | None,
    reason: str | None = None,
) -> Notification:
    type_map = {
        "submitted": NotificationType.FILING_SUBMITTED,
        "accepted": NotificationType.FILING_ACCEPTED,
        "rejected": NotificationType.FILING_REJECTED,
        "returned": NotificationType.FILING_RETURNED,
    }
    notification_type = type_map.get(status, NotificationType.CASE_UPDATE)

    subject = f"Filing #{filing_id} - {status.title()} - {court_name}"
    body_parts = [
        f"Your filing #{filing_id} has been {status}.",
        f"Court: {court_name}",
    ]
    if case_title:
        body_parts.append(f"Case: {case_title}")
    if reason:
        body_parts.append(f"Reason: {reason}")

    return await create_notification(
        db,
        notification_type=notification_type,
        recipient_id=filer_id,
        filing_envelope_id=filing_id,
        subject=subject,
        body="\n".join(body_parts),
    )
