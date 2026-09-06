"""Explicit, recipient-scoped delivery of retained subsequent documents."""

from datetime import UTC
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.api.auth import get_current_user
from app.api.documents import DocumentResponse
from app.config import settings
from app.database import get_db
from app.models.case import CaseParticipant
from app.models.court import Court
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope
from app.models.notification import (
    DeliveryStatus,
    Notification,
    NotificationDeliveryEvent,
    ServiceContact,
    ServiceMethod,
)
from app.models.service_delivery import ServiceEvent, ServicePacket, ServiceRecipient
from app.models.user import User
from app.schemas.service_delivery import ServicePacketCreate
from app.services import access_service
from app.services import service_delivery_service as service
from app.services.email_delivery_service import queue_email
from app.services.service_contact_service import email_context, routing_issues

router = APIRouter(prefix="/service", tags=["Document delivery"])
RecordId = Annotated[int, Path(ge=1, le=2_147_483_647)]
Db = Annotated[AsyncSession, Depends(get_db, scope="function")]
Actor = Annotated[User, Depends(get_current_user)]


class RetryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/filings/{filing_id}/options")
async def delivery_options(filing_id: RecordId, db: Db, actor: Actor, page: int = Query(1, ge=1)):
    filing, case = await service.require_sender(db, actor, filing_id)
    source = await service.current_source(db, filing)
    filters = (CaseParticipant.case_id == case.id, CaseParticipant.is_active.is_(True))
    total = await db.scalar(select(func.count()).select_from(CaseParticipant).where(*filters))
    rows = await db.execute(
        select(CaseParticipant, ServiceContact, User)
        .outerjoin(ServiceContact, ServiceContact.participant_id == CaseParticipant.id)
        .outerjoin(User, User.id == CaseParticipant.user_id)
        .where(*filters)
        .order_by(CaseParticipant.id)
        .offset((page - 1) * 25)
        .limit(25)
    )
    recipients = []
    for participant, contact, account in rows:
        issues = (
            routing_issues(case, participant, account, contact)
            if contact
            else [
                "The court has not reviewed service instructions for this participant.",
            ]
        )
        if contact and contact.case_id != case.id:
            issues = ["The contact's case destination needs court review."]
        if contact and contact.method != ServiceMethod.ELECTRONIC:
            issues.append("Follow these service instructions outside the portal.")
        if account and account.id == actor.id:
            issues.append("This is your own account.")
        recipients.append(
            {
                "participant_id": participant.id,
                "name": participant.party_name,
                "role": participant.role,
                "represented_party_name": participant.represented_party_name,
                "contact_id": contact.id if contact else None,
                "version": contact.version if contact else None,
                "method": contact.method if contact else None,
                "email": contact.email if contact else None,
                "address": contact.address if contact else None,
                "authority": contact.authority if contact else None,
                "issues": issues,
            }
        )
    return {
        "enabled": settings.service_delivery_enabled and settings.email_delivery_enabled,
        "source_transaction_id": source.id,
        "case_number": case.case_number,
        "case_title": case.title,
        "court_name": await db.scalar(select(Court.name).where(Court.id == case.court_id)),
        "documents": service.source_documents(source),
        "recipients": recipients,
        "total": total,
        "page_size": 25,
    }


@router.post("/filings/{filing_id}/deliveries", status_code=201)
async def send_documents(
    filing_id: RecordId,
    data: ServicePacketCreate,
    db: Db,
    actor: Actor,
    idempotency_key: Annotated[UUID, Header()],
):
    # A failed recipient or integrity check must not leave a partial delivery behind.
    async with db.begin_nested():
        packet = await service.create_packet(db, actor.id, filing_id, data, str(idempotency_key))
    return {"packet_id": packet.id}


@router.get("/deliveries")
async def inbox(db: Db, actor: Actor, page: int = Query(1, ge=1)):
    filters = (ServiceRecipient.recipient_id == actor.id,)
    total = await db.scalar(select(func.count()).select_from(ServiceRecipient).where(*filters))
    rows = await db.execute(
        select(
            ServiceRecipient.id,
            ServicePacket.actor_name,
            ServicePacket.created_at,
            Notification.delivery_status,
        )
        .join(ServicePacket, ServicePacket.id == ServiceRecipient.packet_id)
        .join(Notification, Notification.id == ServiceRecipient.notification_id)
        .where(*filters)
        .order_by(ServicePacket.created_at.desc(), ServiceRecipient.id.desc())
        .offset((page - 1) * 25)
        .limit(25)
    )
    # An inbox entry persists after access revocation, but discloses no case title or documents.
    return {
        "deliveries": [
            {
                **dict(row),
                "created_at": row["created_at"].replace(tzinfo=row["created_at"].tzinfo or UTC),
            }
            for row in rows.mappings()
        ],
        "total": total,
        "page_size": 25,
    }


@router.get("/filings/{filing_id}/deliveries")
async def sent_deliveries(filing_id: RecordId, db: Db, actor: Actor, page: int = Query(1, ge=1)):
    filing = await db.scalar(
        select(FilingEnvelope)
        .where(FilingEnvelope.id == filing_id)
        .options(raiseload(FilingEnvelope.documents))
    )
    if filing is None:
        raise HTTPException(404, "Filing not found")
    if filing.filer_id != actor.id and not await access_service.user_is_court_staff_for_court(
        db,
        actor.id,
        filing.court_id,
    ):
        raise HTTPException(403, "Filer or assigned court staff required")
    query = (
        select(
            ServiceRecipient.id,
            ServiceRecipient.packet_id,
            ServiceRecipient.contact_snapshot["name"].as_string().label("name"),
            ServiceRecipient.contact_snapshot["email"].as_string().label("email"),
            ServicePacket.created_at,
            Notification.delivery_status,
        )
        .join(ServicePacket, ServicePacket.id == ServiceRecipient.packet_id)
        .join(Notification, Notification.id == ServiceRecipient.notification_id)
        .where(ServicePacket.filing_id == filing.id)
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.execute(
        query.order_by(ServicePacket.created_at.desc(), ServiceRecipient.id.desc())
        .offset((page - 1) * 25)
        .limit(25)
    )
    return {
        "deliveries": [
            {
                **dict(row),
                "created_at": row["created_at"].replace(tzinfo=row["created_at"].tzinfo or UTC),
            }
            for row in rows.mappings()
        ],
        "total": total,
        "page_size": 25,
    }


@router.get("/deliveries/{delivery_id}")
async def delivery_details(delivery_id: UUID, db: Db, actor: Actor):
    recipient, packet, notice, staff = await service.require_delivery_viewer(
        db, actor, str(delivery_id)
    )
    acknowledged = await db.scalar(
        select(ServiceEvent.occurred_at)
        .where(
            ServiceEvent.service_recipient_id == recipient.id,
            ServiceEvent.action == "acknowledged",
        )
        .limit(1)
    )
    return {
        "id": recipient.id,
        "packet_id": packet.id,
        "filing_id": packet.filing_id,
        "source_transaction_id": packet.source_transaction_id,
        "sender": packet.actor_name,
        "created_at": packet.created_at.replace(tzinfo=packet.created_at.tzinfo or UTC),
        **packet.details,
        "contact": recipient.contact_snapshot,
        "delivery_status": notice.delivery_status,
        "last_error": notice.last_error,
        "message_id": notice.email_message_id,
        "acknowledged_at": acknowledged.replace(tzinfo=acknowledged.tzinfo or UTC)
        if acknowledged
        else None,
        "can_acknowledge": actor.id == recipient.recipient_id and acknowledged is None,
        "can_retry": settings.service_delivery_enabled
        and settings.email_delivery_enabled
        and (staff or actor.id == packet.actor_id)
        and (
            notice.delivery_status
            in (DeliveryStatus.BLOCKED, DeliveryStatus.DISABLED, DeliveryStatus.FAILED)
            or staff
            and notice.delivery_status in (DeliveryStatus.UNKNOWN, DeliveryStatus.LEGACY)
        ),
    }


@router.get("/deliveries/{delivery_id}/events")
async def delivery_events(
    delivery_id: UUID,
    db: Db,
    actor: Actor,
    kind: Literal["portal", "email"] = "portal",
    page: int = Query(1, ge=1),
):
    recipient, _, notice, _ = await service.require_delivery_viewer(db, actor, str(delivery_id))
    if kind == "portal":
        query = select(
            ServiceEvent.id,
            ServiceEvent.action,
            ServiceEvent.occurred_at,
            ServiceEvent.actor_name,
            ServiceEvent.details,
        ).where(
            ServiceEvent.service_recipient_id == recipient.id,
        )
        order = ServiceEvent.id.desc()
    else:
        query = select(
            NotificationDeliveryEvent.id,
            NotificationDeliveryEvent.outcome.label("action"),
            NotificationDeliveryEvent.occurred_at,
            NotificationDeliveryEvent.detail,
            NotificationDeliveryEvent.smtp_code,
            NotificationDeliveryEvent.attempt_number,
        ).where(
            NotificationDeliveryEvent.notification_id == notice.id,
        )
        order = NotificationDeliveryEvent.id.desc()
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.execute(query.order_by(order).offset((page - 1) * 25).limit(25))
    return {
        "events": [
            {
                **dict(row),
                "occurred_at": row["occurred_at"].replace(tzinfo=row["occurred_at"].tzinfo or UTC),
            }
            for row in rows.mappings()
        ],
        "total": total,
        "page_size": 25,
    }


@router.get("/deliveries/{delivery_id}/documents/{document_id}")
async def download_delivery_document(
    delivery_id: UUID, document_id: RecordId, db: Db, actor: Actor
):
    recipient, packet, _, _ = await service.require_delivery_viewer(db, actor, str(delivery_id))
    saved = next((doc for doc in packet.details["documents"] if doc["id"] == document_id), None)
    if saved is None or saved["document_type_code"] in PRIVATE_DOCUMENT_TYPES:
        raise HTTPException(404, "Document not included in this delivery")
    doc = await db.get(FilingDocument, document_id)
    if (
        doc is None
        or doc.envelope_id != packet.filing_id
        or not doc.retained_at
        or doc.document_type_code in PRIVATE_DOCUMENT_TYPES
        or doc.sha256_hash != saved["sha256_hash"]
        or doc.file_size_bytes != saved["file_size_bytes"]
        or doc.mime_type != saved["mime_type"]
    ):
        raise HTTPException(409, "The document no longer matches its retained delivery")
    service.record_service_event(db, recipient, actor, "download_requested", document_id=doc.id)
    return DocumentResponse(doc, integrity=(saved["sha256_hash"], saved["file_size_bytes"]))


@router.post("/deliveries/{delivery_id}/acknowledge")
async def acknowledge_delivery(delivery_id: UUID, db: Db, actor: Actor):
    recipient, _, _, _ = await service.require_delivery_viewer(
        db, actor, str(delivery_id), lock=True
    )
    if actor.id != recipient.recipient_id:
        raise HTTPException(403, "Only the named recipient can acknowledge this delivery")
    existing = await db.scalar(
        select(ServiceEvent.id)
        .where(
            ServiceEvent.service_recipient_id == recipient.id,
            ServiceEvent.action == "acknowledged",
        )
        .limit(1)
    )
    if existing is None:
        service.record_service_event(db, recipient, actor, "acknowledged")
    return {"acknowledged": True}


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(delivery_id: UUID, data: RetryRequest, db: Db, actor: Actor):
    recipient, packet, notice, staff = await service.require_delivery_viewer(
        db,
        actor,
        str(delivery_id),
        lock=True,
    )
    if actor.id != packet.actor_id and not staff:
        raise HTTPException(403, "The sender or assigned court staff must request a retry")
    if notice.delivery_status not in (
        DeliveryStatus.BLOCKED,
        DeliveryStatus.DISABLED,
        DeliveryStatus.FAILED,
        DeliveryStatus.UNKNOWN,
        DeliveryStatus.LEGACY,
    ):
        raise HTTPException(409, "The alert is already queued, sending or accepted by the relay")
    if notice.delivery_status in (DeliveryStatus.UNKNOWN, DeliveryStatus.LEGACY) and not staff:
        raise HTTPException(403, "Court staff must review an uncertain SMTP outcome")
    _, error = await email_context(db, notice.id)
    if error:
        raise HTTPException(409, error)
    await queue_email(db, notice, actor_id=actor.id, reason=data.reason)
    service.record_service_event(db, recipient, actor, "retry_requested", reason=data.reason)
    return {"delivery_status": notice.delivery_status}
