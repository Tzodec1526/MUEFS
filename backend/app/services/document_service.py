import hashlib
import io
import logging
from pathlib import Path
from typing import BinaryIO

from app.config import settings

logger = logging.getLogger(__name__)


def _is_demo_mode() -> bool:
    """Check if running in demo mode (SQLite / no S3)."""
    return "sqlite" in settings.database_url


def _local_storage_path() -> Path:
    """Get local document storage directory for demo mode."""
    p = Path("demo_uploads")
    p.mkdir(exist_ok=True)
    return p


def get_s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
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


def compute_sha256(file_data: bytes) -> str:
    return hashlib.sha256(file_data).hexdigest()


def validate_file_size(file_size: int) -> bool:
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    return file_size <= max_bytes


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


async def upload_document(
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


async def download_document(file_key: str) -> BinaryIO:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        return io.BytesIO(local_path.read_bytes())

    client = get_s3_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=file_key)
    return response["Body"]


async def delete_document(file_key: str) -> None:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        if local_path.exists():
            local_path.unlink()
        return

    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=file_key)


def get_pdf_page_count(file_data: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
        return len(reader.pages)
    except Exception as e:
        logger.warning("Failed to extract PDF page count: %s", e)
        return None


def is_pdf_text_searchable(file_data: bytes) -> bool:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
        if len(reader.pages) == 0:
            return False
        text = reader.pages[0].extract_text()
        return bool(text and text.strip())
    except Exception as e:
        logger.warning("Failed to check PDF text searchability: %s", e)
        return False
