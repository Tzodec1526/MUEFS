from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    recipient = Notification.recipient_id == user_id
    total = await db.scalar(select(func.count()).select_from(Notification).where(recipient)) or 0
    result = await db.execute(
        select(Notification).where(recipient)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return {
        "notifications": [
            {
                "id": n.id,
                "type": n.notification_type,
                "subject": n.subject,
                "body": n.body,
                "delivery_status": n.delivery_status,
                "created_at": n.created_at,
            }
            for n in result.scalars()
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
