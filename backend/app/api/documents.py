import hashlib
import mimetypes
import re
from contextlib import closing
from tempfile import SpooledTemporaryFile
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.types import Receive, Scope, Send

from app.api.auth import get_current_user, get_optional_user
from app.api.params import RecordId
from app.database import get_db
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument
from app.models.user import User
from app.schemas.document import DocumentVerifyResponse
from app.services import access_service, audit_service, document_service
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/documents", tags=["Documents"])


def sanitize_filename(filename: str) -> str:
    """Remove path traversal and special characters from filenames."""
    filename = re.sub(r'[^\w\s\-.]', '', filename)
    filename = filename.strip('. ')
    return filename or "document"


class DocumentResponse(StreamingResponse):
    """Open storage after the request transaction commits, and close it on disconnect."""

    def __init__(
        self, doc: FilingDocument | DocumentPublicCopy, *, integrity: tuple[str, int] | None = None,
    ):
        self.file_key = doc.file_key
        self.integrity = integrity
        safe_filename = sanitize_filename(doc.title)
        extension = mimetypes.guess_extension(doc.mime_type) or ""
        if extension and not safe_filename.lower().endswith(extension):
            safe_filename += extension
        super().__init__(
            content=(), media_type=doc.mime_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_filename)}",
                "Cache-Control": "private, no-store",
            },
        )

    def open_file(self):
        stream = document_service.download_document(self.file_key)
        if self.integrity is None:
            return stream
        # Verify the exact bytes before sending headers. Large deliveries spill to
        # disk; the object is read once and memory stays bounded.
        verified = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        digest, size = hashlib.sha256(), 0
        try:
            with closing(stream):
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    if size > self.integrity[1]:
                        raise HTTPException(409, "Document failed its retained integrity check")
                    verified.write(chunk)
            if (digest.hexdigest(), size) != self.integrity:
                raise HTTPException(409, "Document failed its retained integrity check")
            verified.seek(0)
            return verified
        except BaseException:
            verified.close()
            raise

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            with document_service.storage_errors():
                file_stream = await run_in_threadpool(self.open_file)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Document file is unavailable") from exc

        def chunks():
            while chunk := file_stream.read(64 * 1024):
                yield chunk

        with closing(file_stream):
            self.body_iterator = iterate_in_threadpool(chunks())
            await super().__call__(scope, receive, send)


@router.get("/{document_id}/download")
async def download_document(
    request: Request,
    document_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    user: User | None = Depends(get_optional_user),
):
    """Public download for non-confidential documents on non-sealed, accepted
    filings. Confidential documents and sealed matters require an authorized account."""
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not await access_service.user_may_read_document(db, user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    await audit_service.log_action(
        db,
        user_id=user.id if user else None,
        action="document_download",
        entity_type="filing_document",
        entity_id=document_id,
        details=None,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )

    return DocumentResponse(doc, integrity=(doc.sha256_hash, doc.file_size_bytes))


@router.get("/{document_id}/verify", response_model=DocumentVerifyResponse)
async def verify_document(
    document_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not await access_service.user_may_read_document(db, user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    try:
        current_hash, size = await run_in_threadpool(
            document_service.stored_integrity, doc.file_key,
        )
        is_valid = current_hash == doc.sha256_hash and size == doc.file_size_bytes
    except FileNotFoundError:
        return DocumentVerifyResponse(
            document_id=document_id,
            sha256_hash=doc.sha256_hash,
            is_valid=False,
            message="Unable to verify document - the file is missing from storage",
        )

    return DocumentVerifyResponse(
        document_id=document_id,
        sha256_hash=doc.sha256_hash,
        is_valid=is_valid,
        message=(
            "Document integrity verified"
            if is_valid
            else "Document integrity check failed - hash mismatch"
        ),
    )
