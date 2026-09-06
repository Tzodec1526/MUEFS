"""Prepare, review, publish and withdraw public copies without rewriting filed originals."""

from datetime import UTC
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user, get_optional_user_id
from app.api.document_upload import inspect_upload
from app.api.documents import DocumentResponse
from app.database import get_db
from app.models.audit import AuditLog
from app.models.document_public_copy import DocumentPublicCopy
from app.models.user import User
from app.schemas.document_publication import PublicCopyResponse, PublishCopy, WithholdDocument
from app.schemas.filing import FilingDocumentResponse
from app.services import audit_service, document_service
from app.services import document_publication_service as publication
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(tags=["Document publication"])


@router.get("/clerk/documents/{document_id}/publication")
async def publication_state(
    document_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    doc, filing = await publication.document_context(db, actor, document_id)
    query = select(DocumentPublicCopy).where(DocumentPublicCopy.document_id == document_id)
    rows = await db.scalars(
        query.order_by(DocumentPublicCopy.id.desc()).offset((page - 1) * 25).limit(25)
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    current = await db.get(DocumentPublicCopy, doc.public_copy_id) if doc.public_copy_id else None
    return {
        "document": FilingDocumentResponse.model_validate(doc),
        "filing_id": filing.id,
        "case_id": filing.case_id,
        "court_id": filing.court_id,
        "filing_status": filing.status,
        "version": doc.access_version,
        "publication_block": publication.publication_block(doc, filing),
        "can_withhold": (filing.status.value != "draft" or doc.retained_at is not None)
        and (not doc.is_confidential or doc.public_copy_id is not None),
        "current_copy": PublicCopyResponse.model_validate(current) if current else None,
        "copies": [PublicCopyResponse.model_validate(copy) for copy in rows],
        "total": total or 0,
        "page": page,
    }


@router.post(
    "/clerk/documents/{document_id}/public-copies",
    response_model=PublicCopyResponse,
    status_code=201,
)
async def prepare_copy(
    document_id: int,
    request: Request,
    title: str = Form(..., min_length=1, max_length=500),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    title = title.strip()
    if not title:
        raise HTTPException(422, "A public title is required")
    doc, filing = await publication.document_context(db, actor, document_id)
    if blocked := publication.publication_block(doc, filing):
        raise HTTPException(409, blocked)
    payload, mime, digest, inspection = await inspect_upload(file, require_pdf=True)
    file_key = f"public-copies/{document_id}/{uuid4()}.pdf"
    await run_in_threadpool(document_service.upload_document, payload, file_key, mime)
    try:
        async with db.begin_nested():
            doc, filing = await publication.document_context(
                db, actor, document_id, for_update=True
            )
            if blocked := publication.publication_block(doc, filing):
                raise HTTPException(409, blocked)
            copy = DocumentPublicCopy(
                document_id=doc.id,
                created_by=actor.id,
                title=title,
                file_key=file_key,
                file_size_bytes=len(payload),
                mime_type=mime,
                sha256_hash=digest,
                page_count=inspection.page_count,
                is_text_searchable=inspection.is_text_searchable,
                pii_warnings=inspection.pii_warnings,
            )
            db.add(copy)
            await db.flush()
            await audit_service.log_action(
                db,
                user_id=actor.id,
                action="document.public_copy_prepared",
                entity_type="filing_document",
                entity_id=doc.id,
                details={
                    "copy_id": copy.id,
                    "title": title,
                    "sha256_hash": digest,
                    "actor_name": actor.full_name,
                },
                ip_address=client_ip(request),
                user_agent=client_user_agent(request),
            )
    except Exception:
        await run_in_threadpool(document_service.delete_document, file_key)
        raise
    return copy


@router.post("/clerk/documents/{document_id}/publication")
async def publish_copy(
    document_id: int,
    data: PublishCopy,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    async with db.begin_nested():
        await publication.publish_copy(
            db,
            actor,
            document_id,
            data,
            context={"ip_address": client_ip(request), "user_agent": client_user_agent(request)},
        )
    return {"copy_id": data.copy_id}


@router.post("/clerk/documents/{document_id}/withhold")
async def withhold_document(
    document_id: int,
    data: WithholdDocument,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    async with db.begin_nested():
        await publication.withhold_document(
            db,
            actor,
            document_id,
            data,
            context={"ip_address": client_ip(request), "user_agent": client_user_agent(request)},
        )
    return {"withheld": True}


@router.get("/clerk/documents/{document_id}/publication/history")
async def publication_history(
    document_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    await publication.document_context(db, actor, document_id)
    copies = select(DocumentPublicCopy.id).where(DocumentPublicCopy.document_id == document_id)
    query = select(AuditLog).where(
        or_(
            and_(
                AuditLog.entity_type == "filing_document",
                AuditLog.entity_id == document_id,
                AuditLog.action.in_(["document.public_copy_prepared", "document.withheld"]),
            ),
            and_(
                AuditLog.entity_type == "document_public_copy",
                AuditLog.entity_id.in_(copies),
                AuditLog.action == "public_copy.published",
            ),
        )
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(query.order_by(AuditLog.id.desc()).offset((page - 1) * 25).limit(25))
    return {
        "total": total or 0,
        "events": [
            {
                "id": row.id,
                "action": row.action,
                "details": row.details,
                "actor_name": (row.details or {}).get("actor_name"),
                "occurred_at": row.timestamp.replace(
                    tzinfo=row.timestamp.tzinfo or UTC
                ).isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/document-public-copies/{copy_id}/download")
async def download_public_copy(
    copy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int | None = Depends(get_optional_user_id),
):
    copy = await db.get(DocumentPublicCopy, copy_id)
    if not copy:
        raise HTTPException(404, "Public copy not found")
    if not await publication.may_read_public_copy(db, user_id, copy):
        raise HTTPException(403, "Not authorized to access this copy")
    await audit_service.log_action(
        db,
        user_id=user_id,
        action="public_copy.downloaded",
        entity_type="document_public_copy",
        entity_id=copy.id,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return DocumentResponse(copy)
