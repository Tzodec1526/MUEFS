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
    count_query = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient_id == user_id)
    )
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(Notification)
        .where(Notification.recipient_id == user_id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "notifications": [
            {
                "id": n.id,
                "type": getattr(n.notification_type, 'value', n.notification_type),
                "subject": n.subject,
                "body": n.body,
                "delivery_status": getattr(n.delivery_status, 'value', n.delivery_status),
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
