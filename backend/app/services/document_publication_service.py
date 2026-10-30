from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.user import User
from app.schemas.document_publication import PublicCopyResponse, PublishCopy, WithholdDocument
from app.services import access_service, audit_service, document_service, filing_record_service


async def document_context(
    db: AsyncSession,
    actor: User,
    document_id: int,
    *,
    for_update: bool = False,
    decision: bool = False,
) -> tuple[FilingDocument, FilingEnvelope]:
    doc = await db.get(FilingDocument, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if for_update:
        locked_actor = await db.scalar(
            select(User)
            .where(User.id == actor.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_actor is None:
            raise HTTPException(403, "Account is unavailable")
        actor = locked_actor
        filing = await db.scalar(
            select(FilingEnvelope)
            .where(FilingEnvelope.id == doc.envelope_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        doc = await db.scalar(
            select(FilingDocument)
            .where(FilingDocument.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        filing = await db.get(FilingEnvelope, doc.envelope_id)
    if not actor.is_active or not filing or not doc:
        raise HTTPException(403, "Account or filing is unavailable")
    if not await access_service.user_is_court_staff_for_court(db, actor.id, filing.court_id):
        raise HTTPException(403, "A staff assignment for this court is required")
    if decision and filing.filer_id == actor.id:
        raise HTTPException(403, "Another court reviewer must decide your own filing")
    return doc, filing


def publication_block(doc: FilingDocument, filing: FilingEnvelope) -> str | None:
    if doc.document_type_code in PRIVATE_DOCUMENT_TYPES:
        return "Fee waiver records cannot be published through this workflow"
    if (
        doc.removed_at is not None
        or filing.status != FilingStatus.ACCEPTED
        or filing.case_id is None
    ):
        return "Public copies require a current document on an accepted filing"
    return None


async def publish_copy(
    db: AsyncSession,
    actor: User,
    document_id: int,
    data: PublishCopy,
    *,
    context: dict,
) -> None:
    doc, filing = await document_context(db, actor, document_id, decision=True)
    if doc.access_version != data.expected_version:
        raise HTTPException(409, "Document access changed. Refresh before publishing")
    copy = await db.scalar(
        select(DocumentPublicCopy).where(
            DocumentPublicCopy.id == data.copy_id,
            DocumentPublicCopy.document_id == document_id,
        )
    )
    if not copy:
        raise HTTPException(404, "Public copy not found for this document")
    try:
        digest, size = await run_in_threadpool(document_service.stored_integrity, copy.file_key)
    except FileNotFoundError as exc:
        raise HTTPException(409, "The prepared copy is unavailable. Prepare it again") from exc
    if digest != copy.sha256_hash or size != copy.file_size_bytes:
        raise HTTPException(409, "The prepared copy failed its integrity check. Prepare it again")
    doc, filing = await document_context(
        db, actor, document_id, for_update=True, decision=True,
    )
    if blocked := publication_block(doc, filing):
        raise HTTPException(409, blocked)
    if doc.access_version != data.expected_version:
        raise HTTPException(409, "Document access changed. Refresh before publishing")
    if doc.public_copy_id == copy.id and doc.is_confidential:
        return
    before = {"original_restricted": doc.is_confidential, "public_copy_id": doc.public_copy_id}
    version = await db.scalar(
        update(FilingDocument)
        .where(
            FilingDocument.id == document_id,
            FilingDocument.access_version == data.expected_version,
        )
        .values(
            is_confidential=True, public_copy_id=copy.id, access_version=data.expected_version + 1
        )
        .returning(FilingDocument.access_version)
    )
    if version is None:
        raise HTTPException(409, "Document access changed. Refresh before publishing")
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="public_copy.published",
        entity_type="document_public_copy",
        entity_id=copy.id,
        details={
            "document_id": document_id,
            "reason": data.reason,
            "actor_name": actor.full_name,
            "reviewed": True,
            "before": before,
            "after": {"original_restricted": True, "public_copy_id": copy.id},
        },
        **context,
    )
    await filing_record_service.record_transaction(
        db,
        filing,
        "public_copy_published",
        actor.id,
        reason=data.reason,
        details={
            "document_id": document_id,
            "public_copy": PublicCopyResponse.model_validate(copy).model_dump(mode="json"),
        },
    )


async def withhold_document(
    db: AsyncSession,
    actor: User,
    document_id: int,
    data: WithholdDocument,
    *,
    context: dict,
) -> None:
    doc, filing = await document_context(
        db, actor, document_id, for_update=True, decision=True,
    )
    if doc.access_version != data.expected_version:
        raise HTTPException(409, "Document access changed. Refresh before withholding")
    if filing.status == FilingStatus.DRAFT and doc.retained_at is None:
        raise HTTPException(409, "The filer has not submitted this document")
    if doc.is_confidential and doc.public_copy_id is None:
        return
    before = {"original_restricted": doc.is_confidential, "public_copy_id": doc.public_copy_id}
    version = await db.scalar(
        update(FilingDocument)
        .where(
            FilingDocument.id == document_id,
            FilingDocument.access_version == data.expected_version,
        )
        .values(is_confidential=True, public_copy_id=None, access_version=data.expected_version + 1)
        .returning(FilingDocument.access_version)
    )
    if version is None:
        raise HTTPException(409, "Document access changed. Refresh before withholding")
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="document.withheld",
        entity_type="filing_document",
        entity_id=doc.id,
        details={
            "reason": data.reason,
            "before": before,
            "actor_name": actor.full_name,
            "after": {"original_restricted": True, "public_copy_id": None},
        },
        **context,
    )
    await filing_record_service.record_transaction(
        db,
        filing,
        "document_withheld",
        actor.id,
        reason=data.reason,
        details={"document_id": document_id, "withdrawn_copy_id": before["public_copy_id"]},
    )


async def may_read_public_copy(
    db: AsyncSession,
    user: User | None,
    copy: DocumentPublicCopy,
) -> bool:
    user_id = user.id if user else None
    doc = await db.get(FilingDocument, copy.document_id)
    filing = await db.get(FilingEnvelope, doc.envelope_id) if doc else None
    if doc is None or filing is None:
        return False
    if await access_service.user_is_court_staff_for_court(db, user_id, filing.court_id):
        return True
    if user_id == filing.filer_id:
        return bool(
            await db.scalar(
                select(FilingTransaction.id)
                .where(
                    FilingTransaction.filing_id == filing.id,
                    FilingTransaction.event_type == "public_copy_published",
                    FilingTransaction.details["public_copy"]["id"].as_integer() == copy.id,
                )
                .limit(1)
            )
        )
    if doc.public_copy_id != copy.id or publication_block(doc, filing) or filing.case_id is None:
        return False
    return await access_service.user_may_read_case(db, user, filing.case_id)
