
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.services.email_delivery_service import queue_email


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

    label = {
        "waiver_referred": "Fee waiver referred for judicial review",
        "waiver_granted": "Fee waiver granted",
        "waiver_denied": "Fee waiver denied",
        "payment_recorded": "Payment recorded",
        "filing_date_assessed": "Filing date assessed using court calendar",
    }.get(status, status.replace("_", " ").title())
    subject = f"Filing #{filing_id} - {label} - {court_name}"
    body_parts = [
        f"Filing #{filing_id}: {label}.",
        f"Court: {court_name}",
    ]
    if case_title:
        body_parts.append(f"Case: {case_title}")
    if reason:
        body_parts.append(f"Reason: {reason}")

    notification = Notification(
        notification_type=notification_type,
        recipient_id=filer_id,
        filing_envelope_id=filing_id,
        subject=subject,
        body="\n".join(body_parts),
    )
    db.add(notification)
    await db.flush()
    await queue_email(db, notification)
    return notification
