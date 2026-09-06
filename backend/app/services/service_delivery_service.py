"""Explicit document delivery with retained contents and recipient-scoped access."""

import hashlib
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import false, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, raiseload
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.case import COUNSEL_ROLES, Case, CaseParticipant
from app.models.court import Court
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import DeliveryStatus, Notification, NotificationType, ServiceContact
from app.models.service_delivery import ServiceEvent, ServicePacket, ServiceRecipient
from app.models.user import User, UserType
from app.schemas.filing import FilingDocumentResponse
from app.schemas.service_delivery import ServicePacketCreate
from app.services import access_service, document_service
from app.services.email_delivery_service import queue_email, validate_email_config
from app.services.service_contact_service import contact_snapshot, routing_issues


async def require_sender(
    db: AsyncSession,
    actor: User,
    filing_id: int,
    *,
    lock: bool = False,
) -> tuple[FilingEnvelope, Case]:
    query = (
        select(FilingEnvelope)
        .where(FilingEnvelope.id == filing_id)
        .options(
            raiseload(FilingEnvelope.documents),
        )
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    filing = await db.scalar(query)
    if filing is None:
        raise HTTPException(404, "Filing not found")
    staff = await access_service.user_is_court_staff_for_court(db, actor.id, filing.court_id)
    if filing.filer_id != actor.id and not staff:
        raise HTTPException(
            403, "The filer or assigned court staff must select documents for delivery"
        )
    if filing.case_id is None or filing.filing_type not in ("subsequent", "motion", "service_only"):
        raise HTTPException(
            409,
            "This workflow is for subsequent documents on an existing case. "
            "Follow the court's service procedure for case-initiating documents.",
        )
    case_query = select(Case).where(Case.id == filing.case_id)
    if lock:
        case_query = case_query.with_for_update(read=True).execution_options(populate_existing=True)
    case = await db.scalar(case_query)
    if case is None or case.court_id != filing.court_id:
        raise HTTPException(409, "The filing's case destination needs court review")
    if (
        not actor.is_active
        or not actor.verified_email
        or actor.verified_email != actor.email.strip().lower()
    ):
        raise HTTPException(403, "Document delivery requires an active account with verified email")
    if not staff:
        counsel = (
            CaseParticipant.attorney_bar_number == actor.bar_number
            if actor.user_type == UserType.ATTORNEY
            and actor.bar_number
            and actor.bar_number_verified
            else false()
        )
        participation = await db.scalar(
            select(CaseParticipant.id)
            .where(
                CaseParticipant.case_id == case.id,
                CaseParticipant.user_id == actor.id,
                CaseParticipant.is_active.is_(True),
                CaseParticipant.reviewed_at.is_not(None),
                or_(CaseParticipant.role.not_in(COUNSEL_ROLES), counsel),
            )
            .limit(1)
        )
        if not participation or not await access_service.user_may_read_case(db, actor.id, case.id):
            raise HTTPException(
                403, "Court-reviewed case participation is required to send documents"
            )
    return filing, case


async def current_source(db: AsyncSession, filing: FilingEnvelope) -> FilingTransaction:
    if filing.status not in (
        FilingStatus.SUBMITTED,
        FilingStatus.UNDER_REVIEW,
        FilingStatus.ACCEPTED,
        FilingStatus.SERVED,
    ):
        raise HTTPException(409, "Record the current documents before selecting them for delivery")
    sources = list(
        await db.scalars(
            select(FilingTransaction)
            .where(
                FilingTransaction.filing_id == filing.id,
                FilingTransaction.submission_number == filing.submission_count,
                FilingTransaction.event_type.in_(("submitted", "service_recorded")),
            )
            .limit(2)
        )
    )
    if len(sources) != 1:
        raise HTTPException(409, "This filing needs a retained submission receipt before delivery")
    source = sources[0]
    if (
        source.details.get("case_id") != filing.case_id
        or source.details.get("court_id") != filing.court_id
        or source.details.get("filing_type") != filing.filing_type
    ):
        raise HTTPException(409, "The retained receipt and filing destination need court review")
    return source


def source_documents(source: FilingTransaction) -> list[dict]:
    try:
        records = [
            FilingDocumentResponse.model_validate(record).model_dump(mode="json")
            for record in source.details["documents"]
        ]
        if len({record["id"] for record in records}) != len(records):
            raise ValueError("Duplicate documents")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(409, "The retained document manifest needs court review") from exc
    return [
        record for record in records if record["document_type_code"] not in PRIVATE_DOCUMENT_TYPES
    ]


async def create_packet(
    db: AsyncSession,
    actor_id: int,
    filing_id: int,
    data: ServicePacketCreate,
    idempotency_key: str,
) -> ServicePacket:
    actor = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.is_active:
        raise HTTPException(403, "Account is unavailable")
    request_data = {
        "filing_id": filing_id,
        "source_transaction_id": str(data.source_transaction_id),
        "documents": sorted(data.document_ids),
        "recipients": sorted((item.contact_id, item.version) for item in data.recipients),
    }
    fingerprint = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
    existing = await db.scalar(
        select(ServicePacket).where(
            ServicePacket.actor_id == actor_id,
            ServicePacket.idempotency_key == idempotency_key,
        )
    )
    if existing:
        if existing.request_sha256 != fingerprint:
            raise HTTPException(409, "This delivery key was already used for different selections")
        return existing
    if not settings.service_delivery_enabled or not settings.email_delivery_enabled:
        raise HTTPException(
            503, "Document delivery is not enabled. Follow the court's service instructions"
        )
    validate_email_config()
    filing, case = await require_sender(db, actor, filing_id, lock=True)
    source = await current_source(db, filing)
    if source.id != str(data.source_transaction_id):
        raise HTTPException(
            409, "The filing was resubmitted. Review the current documents before sending"
        )
    manifest = {record["id"]: record for record in source_documents(source)}
    if not set(data.document_ids) <= manifest.keys():
        raise HTTPException(
            422, "Select only documents from this receipt. Fee-waiver material cannot be sent"
        )
    choices = {item.contact_id: item.version for item in data.recipients}
    rows = (
        await db.execute(
            select(ServiceContact, CaseParticipant, User)
            .join(CaseParticipant, CaseParticipant.id == ServiceContact.participant_id)
            .join(User, User.id == CaseParticipant.user_id)
            .where(
                ServiceContact.id.in_(choices),
                ServiceContact.case_id == case.id,
                CaseParticipant.case_id == case.id,
            )
            .order_by(ServiceContact.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(rows) != len(choices):
        raise HTTPException(422, "Select reviewed electronic contacts from this case")
    accounts = set()
    for contact, participant, account in rows:
        if contact.method != "electronic" or contact.version != choices[contact.id]:
            raise HTTPException(
                409, "The selected service instructions changed. Refresh before sending"
            )
        issues = routing_issues(case, participant, account, contact)
        if issues:
            raise HTTPException(409, " ".join(issues))
        if account.id == actor.id or account.id in accounts:
            raise HTTPException(
                422, "Select each recipient account once, excluding your own account"
            )
        accounts.add(account.id)
    documents = list(
        await db.scalars(
            select(FilingDocument).where(
                FilingDocument.id.in_(data.document_ids),
                FilingDocument.envelope_id == filing.id,
                FilingDocument.retained_at.is_not(None),
            )
        )
    )
    if len(documents) != len(data.document_ids):
        raise HTTPException(409, "A selected retained document is unavailable")
    for document in documents:
        saved = manifest[document.id]
        if (
            document.document_type_code in PRIVATE_DOCUMENT_TYPES
            or document.sha256_hash != saved["sha256_hash"]
            or document.file_size_bytes != saved["file_size_bytes"]
            or document.mime_type != saved["mime_type"]
        ):
            raise HTTPException(409, "A selected document no longer matches its retained receipt")
        try:
            digest, size = await run_in_threadpool(
                document_service.stored_integrity, document.file_key
            )
        except OSError as exc:
            raise HTTPException(409, "A selected document could not be read from storage") from exc
        if digest != saved["sha256_hash"] or size != saved["file_size_bytes"]:
            raise HTTPException(409, "A selected document failed its integrity check")
    packet = ServicePacket(
        case_id=case.id,
        filing_id=filing.id,
        source_transaction_id=source.id,
        actor_id=actor.id,
        actor_name=actor.full_name,
        created_at=datetime.now(UTC),
        idempotency_key=idempotency_key,
        request_sha256=fingerprint,
        details={
            "court_name": await db.scalar(select(Court.name).where(Court.id == case.court_id)),
            "case_number": case.case_number,
            "case_title": case.title,
            "documents": [manifest[doc_id] for doc_id in sorted(data.document_ids)],
        },
    )
    try:
        async with db.begin_nested():
            db.add(packet)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(
            select(ServicePacket).where(
                ServicePacket.actor_id == actor_id,
                ServicePacket.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_sha256 != fingerprint:
            raise HTTPException(
                409, "This delivery key was already used for different selections"
            ) from None
        return existing
    for contact, _participant, account in rows:
        notice = Notification(
            notification_type=NotificationType.SERVICE_OF_PROCESS,
            recipient_id=account.id,
            filing_envelope_id=filing.id,
            subject="Documents are available for your case",
            body="A document package is available in your secure delivery inbox. "
            "Open the delivery to inspect its contents and history.",
        )
        db.add(notice)
        await db.flush()
        db.add(
            ServiceRecipient(
                packet_id=packet.id,
                recipient_id=account.id,
                contact_id=contact.id,
                contact_version=contact.version,
                contact_snapshot=contact_snapshot(contact),
                notification_id=notice.id,
            )
        )
        await db.flush()
        await queue_email(
            db, notice, actor_id=actor.id, reason="Explicit document delivery requested"
        )
        if notice.delivery_status != DeliveryStatus.PENDING:
            raise HTTPException(409, notice.last_error or "The delivery alert could not be queued")
    return packet


async def require_delivery_viewer(
    db: AsyncSession,
    actor: User,
    delivery_id: str,
    *,
    lock: bool = False,
) -> tuple[ServiceRecipient, ServicePacket, Notification, bool]:
    recipient = await db.get(ServiceRecipient, delivery_id)
    if recipient is None:
        raise HTTPException(404, "Delivery not found")
    packet = await db.get(ServicePacket, recipient.packet_id)
    assert packet is not None
    case = await db.get(Case, packet.case_id)
    assert case is not None
    staff = await access_service.user_is_court_staff_for_court(db, actor.id, case.court_id)
    if not actor.is_active:
        raise HTTPException(403, "Account is unavailable")
    if actor.id != packet.actor_id and not staff:
        if actor.id != recipient.recipient_id:
            raise HTTPException(403, "Delivery recipient, sender or assigned court staff required")
        participant_id = recipient.contact_snapshot.get("participant_id")
        participant = await db.get(CaseParticipant, participant_id) if participant_id else None
        if (
            participant is None
            or participant.case_id != case.id
            or participant.user_id != actor.id
            or not participant.is_active
            or not participant.reviewed_at
            or participant.role in COUNSEL_ROLES
            and (
                actor.user_type != UserType.ATTORNEY
                or not actor.bar_number_verified
                or not actor.bar_number
                or actor.bar_number != participant.attorney_bar_number
            )
            or not await access_service.user_may_read_case(db, actor.id, case.id)
        ):
            raise HTTPException(403, "Current case participation and access are required")
        # The stable account retains past deliveries when its service email changes.
        # A new address does not redirect an old delivery to another account.
    query = (
        select(Notification)
        .where(Notification.id == recipient.notification_id)
        .options(
            defer(Notification.email_message),
        )
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    notice = await db.scalar(query)
    assert notice is not None
    return recipient, packet, notice, staff


def record_service_event(
    db: AsyncSession,
    recipient: ServiceRecipient,
    actor: User,
    action: str,
    **details,
) -> ServiceEvent:
    event = ServiceEvent(
        service_recipient_id=recipient.id,
        action=action,
        actor_id=actor.id,
        actor_name=actor.full_name,
        occurred_at=datetime.now(UTC),
        details=details,
    )
    db.add(event)
    return event
