"""Async notification delivery tasks via Celery."""

from app.tasks import celery_app


@celery_app.task(name="send_email_notification")
def send_email_notification(
    recipient_email: str,
    subject: str,
    body: str,
    notification_id: int,
) -> dict:
    """Send an email notification."""
    # In production: send via aiosmtplib
    return {
        "notification_id": notification_id,
        "status": "sent",
        "recipient": recipient_email,
    }
