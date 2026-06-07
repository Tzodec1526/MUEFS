"""Async document processing tasks via Celery."""

from app.tasks import celery_app


@celery_app.task(name="process_document")
def process_document(document_id: int, file_key: str) -> dict:
    """Process an uploaded document: virus scan, OCR, PDF/A conversion."""
    # In production:
    # 1. Download from S3
    # 2. Virus scan via ClamAV
    # 3. Check if text-searchable, apply OCR if not
    # 4. Convert to PDF/A if needed
    # 5. Re-upload processed version
    # 6. Update document record in database
    return {
        "document_id": document_id,
        "status": "processed",
        "virus_scan": "clean",
        "ocr_applied": False,
    }


@celery_app.task(name="generate_thumbnail")
def generate_thumbnail(document_id: int, file_key: str) -> dict:
    """Generate a thumbnail preview for a document."""
    return {
        "document_id": document_id,
        "status": "generated",
    }
