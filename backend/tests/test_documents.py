"""Tests for document-related functionality."""


import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.document_service import inspect_pdf, validate_mime_type
from app.utils.pdf import check_pii_patterns
from tests.test_document_publication import publication_pdf


def test_validate_mime_type():
    assert validate_mime_type("application/pdf") is True
    assert validate_mime_type("application/msword") is True
    assert validate_mime_type("text/plain") is True
    assert validate_mime_type("image/jpeg") is True
    assert validate_mime_type("image/png") is True
    assert validate_mime_type("application/rtf") is True
    assert validate_mime_type("application/zip") is False
    assert validate_mime_type("text/html") is False
    assert validate_mime_type("application/javascript") is False


def test_check_pii_ssn():
    warnings = check_pii_patterns("SSN: 123-45-6789")
    assert len(warnings) > 0
    assert any("Social Security" in w for w in warnings)


def test_check_pii_no_pii():
    warnings = check_pii_patterns("This is a normal legal document with no PII.")
    assert len(warnings) == 0


def test_check_pii_dob():
    warnings = check_pii_patterns("Date of Birth: 01/15/1990")
    assert any("date of birth" in w.lower() for w in warnings)


def test_check_pii_financial():
    warnings = check_pii_patterns("Account number 1234567890123456")
    assert any("financial" in w.lower() for w in warnings)


def test_pdf_inspection_samples_text_once_and_deduplicates_pii(monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)  # A scanned cover must not hide later text.
    for _ in range(2):
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }),
            }),
        })
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 10 100 Td (SSN: 123-45-6789) Tj ET")
        page[NameObject("/Contents")] = content
    buffer = io.BytesIO()
    writer.write(buffer)

    readers = []

    def counted_reader(*args, **kwargs):
        reader = PdfReader(*args, **kwargs)
        readers.append(reader)
        return reader

    monkeypatch.setattr("pypdf.PdfReader", counted_reader)
    inspection = inspect_pdf(buffer.getvalue())
    assert len(readers) == 1
    assert inspection.page_count == 3
    assert inspection.is_text_searchable
    assert len(inspection.pii_warnings) == 1
    assert "Social Security" in inspection.pii_warnings[0]


def test_pdf_inspection_handles_malformed_files_and_limits_sampling():
    broken = inspect_pdf(b"not a PDF")
    assert broken.page_count is None
    assert not broken.is_text_searchable
    assert broken.pii_warnings == []

    # A page with text and an SSN shows whether sampling actually stops at the limit.
    record = publication_pdf("SSN 123-45-6789")
    unsampled = inspect_pdf(record, max_pages=0)
    assert unsampled.page_count == 1
    assert not unsampled.is_text_searchable
    assert unsampled.pii_warnings == []
    sampled = inspect_pdf(record, max_pages=1)
    assert sampled.is_text_searchable and sampled.pii_warnings
