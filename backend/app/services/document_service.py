import hashlib
import io
import logging
import shutil
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import BinaryIO

from app.config import settings

logger = logging.getLogger(__name__)


class StorageUnavailableError(OSError):
    """Storage could not complete the operation. A missing file is FileNotFoundError."""
    pass


class StorageQuotaExceededError(Exception):
    """The upload does not fit in the storage allotted to it."""
    pass


@dataclass(frozen=True)
class LocalStorageScope:
    """A private upload folder over the shared local root (hosted-demo sandboxes).

    Writes and deletes stay inside `root`; reads fall back to the shared root, where the
    seeded sample documents that every sandbox references live."""

    root: Path
    quota_bytes: int


# Set per request by the hosted demo; unscoped everywhere else.
storage_scope: ContextVar[LocalStorageScope | None] = ContextVar("storage_scope", default=None)

# Scoped uploads leave this much disk free for sandbox databases and the process.
_SCOPED_FREE_SPACE_RESERVE = 1024 * 1024 * 1024


def uses_local_storage() -> bool:
    """SQLite deployments (the demos) keep documents on disk instead of S3."""
    return "sqlite" in settings.database_url


@contextmanager
def storage_errors() -> Iterator[None]:
    """Report outages as StorageUnavailableError and missing objects as FileNotFoundError."""
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        yield
    except (FileNotFoundError, StorageUnavailableError):
        raise
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            raise FileNotFoundError("Document file is unavailable") from exc
        raise StorageUnavailableError("Document storage refused the request") from exc
    except (BotoCoreError, OSError) as exc:
        raise StorageUnavailableError("Document storage is unavailable") from exc


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


def _resolved(path: Path) -> Path:
    return Path(str(path.resolve()).removeprefix("\\\\?\\"))


def _within(root: Path, file_key: str) -> Path:
    """Resolve a key under root, refusing keys that escape it."""
    base = _resolved(root)
    local_path = _resolved(base / file_key)
    if not local_path.is_relative_to(base):
        raise ValueError("Invalid file key: path traversal detected")
    return local_path


def _writable_path(file_key: str) -> Path:
    scope = storage_scope.get()
    return _within(scope.root if scope else _local_storage_path(), file_key)


def _readable_path(file_key: str) -> Path:
    scope = storage_scope.get()
    if scope is not None:
        private = _within(scope.root, file_key)
        if private.exists():
            return private
    return _within(_local_storage_path(), file_key)


def _require_room(scope: LocalStorageScope, size: int) -> None:
    # Concurrent uploads can each pass this check; the disk reserve still bounds the total.
    used = sum(
        f.stat().st_size for f in scope.root.rglob("*") if f.is_file()
    ) if scope.root.exists() else 0
    if used + size > scope.quota_bytes:
        raise StorageQuotaExceededError(
            "This demo session has used its document storage. Remove draft documents "
            "or start a new session to upload more."
        )
    existing = next(p for p in (scope.root, *scope.root.parents) if p.exists())
    if shutil.disk_usage(existing).free - size < _SCOPED_FREE_SPACE_RESERVE:
        raise StorageQuotaExceededError(
            "The demo's document storage is full. Please try again later."
        )


def ensure_bucket() -> None:
    """Create the configured bucket for a disposable local stack.

    Court deployments provision their own bucket and its policies."""
    if uses_local_storage():
        return
    from botocore.exceptions import ClientError

    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket_name)


def upload_document(
    file_data: bytes,
    file_key: str,
    content_type: str,
) -> str:
    with storage_errors():
        if uses_local_storage():
            local_path = _writable_path(file_key)
            scope = storage_scope.get()
            if scope is not None:
                _require_room(scope, len(file_data))
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
    with storage_errors():
        if uses_local_storage():
            return _readable_path(file_key).open("rb")
        response = get_s3_client().get_object(Bucket=settings.s3_bucket_name, Key=file_key)
    return response["Body"]


def stored_integrity(file_key: str) -> tuple[str, int]:
    with storage_errors(), closing(download_document(file_key)) as stream:
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size


def delete_document(file_key: str) -> None:
    with storage_errors():
        if uses_local_storage():
            # A sandbox deletes only its own files, never the shared seeded samples.
            _writable_path(file_key).unlink(missing_ok=True)
            return
        get_s3_client().delete_object(Bucket=settings.s3_bucket_name, Key=file_key)


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
