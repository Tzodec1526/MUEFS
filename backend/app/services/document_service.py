import hashlib
import io
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


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


async def upload_document(
    file_data: bytes,
    file_key: str,
    content_type: str,
) -> str:
    client = get_s3_client()
    client.upload_fileobj(
        io.BytesIO(file_data),
        settings.s3_bucket_name,
        file_key,
        ExtraArgs={"ContentType": content_type},
    )
    return file_key


async def download_document(file_key: str) -> BinaryIO:
    client = get_s3_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=file_key)
    return response["Body"]


async def delete_document(file_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=file_key)


def get_pdf_page_count(file_data: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
        return len(reader.pages)
    except Exception:
        return None


def is_pdf_text_searchable(file_data: bytes) -> bool:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
        if len(reader.pages) == 0:
            return False
        text = reader.pages[0].extract_text()
        return bool(text and text.strip())
    except Exception:
        return False
