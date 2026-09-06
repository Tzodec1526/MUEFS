import hashlib
import io
import logging
from contextlib import closing
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import BinaryIO

from app.config import settings

logger = logging.getLogger(__name__)


def _is_demo_mode() -> bool:
    """Check if running in demo mode (SQLite / no S3)."""
    return "sqlite" in settings.database_url


def _local_storage_path() -> Path:
    """Only uploads create directories; reading missing storage must have no side effects."""
    return Path(settings.local_storage_path)


@cache
def get_s3_client():
    """Reuse a process-local connection pool; settings are loaded at process startup."""
    import boto3
    from botocore.config import Config
    # Independent sessions also make concurrent first calls safe; boto3's shared
    # default session must not create clients concurrently in upload worker threads.
    return boto3.session.Session().client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def detect_mime_type(file_data: bytes) -> str:
    """Detect MIME type from file content using python-magic."""
    try:
        import magic
        return magic.from_buffer(file_data[:2048], mime=True)
    except Exception:
        return "application/octet-stream"


def resolve_upload_mime_type(file_data: bytes, http_type: str | None) -> str:
    """Pick a MIME type for an upload; strict mode rejects unknown content."""
    detected = detect_mime_type(file_data)
    if detected != "application/octet-stream":
        return detected
    if settings.strict_mime_detection_enabled:
        raise ValueError(
            "Could not verify file type from content; upload rejected"
        )
    return http_type or "application/octet-stream"


def validate_mime_type(mime_type: str) -> bool:
    allowed = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "application/rtf",
        "image/tiff",
        "image/jpeg",
        "image/png",
    }
    return mime_type in allowed


def _safe_local_path(file_key: str) -> Path:
    """Resolve local path and verify it stays within the storage directory."""
    base = _local_storage_path().resolve()
    local_path = (base / file_key).resolve()
    if not local_path.is_relative_to(base):
        raise ValueError("Invalid file key: path traversal detected")
    return local_path


def upload_document(
    file_data: bytes,
    file_key: str,
    content_type: str,
) -> str:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(file_data)
        return file_key

    client = get_s3_client()
    client.upload_fileobj(
        io.BytesIO(file_data),
        settings.s3_bucket_name,
        file_key,
        ExtraArgs={"ContentType": content_type},
    )
    return file_key


def download_document(file_key: str) -> BinaryIO:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        return local_path.open("rb")

    from botocore.exceptions import ClientError

    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=file_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            raise FileNotFoundError("Document file is unavailable") from exc
        raise
    return response["Body"]


def stored_integrity(file_key: str) -> tuple[str, int]:
    with closing(download_document(file_key)) as stream:
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size


def delete_document(file_key: str) -> None:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        if local_path.exists():
            local_path.unlink()
        return

    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=file_key)


@dataclass
class PdfInspection:
    page_count: int | None = None
    is_text_searchable: bool = False
    pii_warnings: list[str] = field(default_factory=list)


def inspect_pdf(file_data: bytes, max_pages: int = 5) -> PdfInspection:
    """Parse once and reuse sampled text for searchability and advisory PII checks."""
    from app.utils.pdf import check_pii_patterns

    inspection = PdfInspection()
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
        inspection.page_count = len(reader.pages)
        for page in reader.pages[:max_pages]:
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("Failed to extract PDF page text: %s", exc)
                continue
            if text.strip():
                inspection.is_text_searchable = True
            for w in check_pii_patterns(text):
                if w not in inspection.pii_warnings:
                    inspection.pii_warnings.append(w)
    except Exception as e:
        logger.warning("Failed to inspect PDF: %s", e)
    return inspection
