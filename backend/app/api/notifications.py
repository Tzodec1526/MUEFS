from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.api.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models.filing import FilingEnvelope
from app.models.notification import DeliveryStatus, Notification, NotificationDeliveryEvent
from app.services.access_service import user_is_court_staff_for_court
from app.services.email_delivery_service import queue_email

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class RetryRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


def _timestamp(value: datetime | None) -> str | None:
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat() if value else None


@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    court_id: int | None = None,
    delivery_status: DeliveryStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    if court_id is None:
        scope = Notification.recipient_id == user_id
    else:
        if not await user_is_court_staff_for_court(db, user_id, court_id):
            raise HTTPException(status_code=403, detail="Court staff assignment required")
        scope = Notification.filing_envelope_id.in_(
            select(FilingEnvelope.id).where(FilingEnvelope.court_id == court_id)
        )
    filters = [scope]
    if delivery_status is not None:
        filters.append(Notification.delivery_status == delivery_status)
    total = await db.scalar(select(func.count()).select_from(Notification).where(*filters)) or 0
    rows = await db.scalars(
        select(Notification)
        .options(defer(Notification.email_message))
        .where(*filters)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "notifications": [
            {
                "id": n.id,
                "filing_envelope_id": n.filing_envelope_id,
                "type": n.notification_type,
                "subject": n.subject,
                "body": n.body,
                "delivery_status": n.delivery_status,
                "email_recipient": n.email_recipient,
                "attempt_count": n.attempt_count,
                "last_error": n.last_error,
                "created_at": _timestamp(n.created_at),
                "sent_at": _timestamp(n.sent_at),
                "next_attempt_at": _timestamp(n.next_attempt_at),
            }
            for n in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "email_enabled": settings.email_delivery_enabled,
    }


async def _notice_for_viewer(
    db: AsyncSession, notice_id: int, user_id: int, *, lock: bool = False
) -> tuple[Notification, bool]:
    query = select(Notification).where(Notification.id == notice_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    notice = await db.scalar(query)
    if notice is None:
        raise HTTPException(status_code=404, detail="Notice not found")
    filing = (
        await db.get(FilingEnvelope, notice.filing_envelope_id)
        if notice.filing_envelope_id
        else None
    )
    staff = bool(filing and await user_is_court_staff_for_court(db, user_id, filing.court_id))
    if notice.recipient_id != user_id and not staff:
        raise HTTPException(
            status_code=403, detail="Notice recipient or assigned court staff required"
        )
    return notice, staff


@router.get("/{notice_id}/delivery")
async def delivery_history(
    notice_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    notice, staff = await _notice_for_viewer(db, notice_id, user_id)
    total = (
        await db.scalar(
            select(func.count())
            .select_from(NotificationDeliveryEvent)
            .where(NotificationDeliveryEvent.notification_id == notice.id)
        )
        or 0
    )
    # Message bodies are retained in the archive but omitted from list responses.
    rows = await db.execute(
        select(
            NotificationDeliveryEvent.id,
            NotificationDeliveryEvent.attempt_number,
            NotificationDeliveryEvent.outcome,
            NotificationDeliveryEvent.occurred_at,
            NotificationDeliveryEvent.detail,
            NotificationDeliveryEvent.smtp_code,
        )
        .where(NotificationDeliveryEvent.notification_id == notice.id)
        .order_by(NotificationDeliveryEvent.id.desc())
        .offset((page - 1) * 25)
        .limit(25)
    )
    return {
        "events": [
            {**dict(row), "occurred_at": _timestamp(row["occurred_at"])} for row in rows.mappings()
        ],
        "total": total,
        "page": page,
        "message_id": notice.email_message_id,
        "can_retry": settings.email_delivery_enabled
        and (
            notice.delivery_status
            in (DeliveryStatus.DISABLED, DeliveryStatus.BLOCKED, DeliveryStatus.FAILED)
            or notice.delivery_status in (DeliveryStatus.UNKNOWN, DeliveryStatus.LEGACY)
            and staff
        ),
    }


@router.post("/{notice_id}/retry")
async def retry_delivery(
    notice_id: int,
    data: RetryRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    notice, staff = await _notice_for_viewer(db, notice_id, user_id, lock=True)
    if not settings.email_delivery_enabled:
        raise HTTPException(status_code=503, detail="Email delivery is not enabled")
    if not data.reason.strip():
        raise HTTPException(status_code=400, detail="A reason for retrying is required")
    if notice.delivery_status not in (
        DeliveryStatus.DISABLED,
        DeliveryStatus.BLOCKED,
        DeliveryStatus.FAILED,
        DeliveryStatus.UNKNOWN,
        DeliveryStatus.LEGACY,
    ):
        raise HTTPException(status_code=409, detail="Notice is already queued, sending or sent")
    if notice.delivery_status in (DeliveryStatus.UNKNOWN, DeliveryStatus.LEGACY) and not staff:
        raise HTTPException(status_code=403, detail="Court staff must review an uncertain outcome")
    await queue_email(db, notice, actor_id=user_id, reason=data.reason.strip())
    if notice.delivery_status == DeliveryStatus.BLOCKED:
        raise HTTPException(status_code=409, detail=notice.last_error)
    return {"delivery_status": notice.delivery_status}
