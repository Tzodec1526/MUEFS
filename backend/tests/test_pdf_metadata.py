"""Unified PDF parsing helper."""

import io

from pypdf import PdfWriter

from app.services.document_service import parse_pdf_metadata


def _empty_pdf_bytes(pages: int = 1) -> bytes:
    """A minimal valid PDF with the requested page count (no embedded text)."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_parse_pdf_metadata_returns_page_count():
    meta = parse_pdf_metadata(_empty_pdf_bytes(pages=3))
    assert meta.page_count == 3


def test_parse_pdf_metadata_handles_invalid_bytes():
    meta = parse_pdf_metadata(b"not a pdf at all")
    assert meta.page_count is None
    assert meta.is_text_searchable is False
    assert meta.pii_warnings == []


def test_parse_pdf_metadata_pii_scan_skips_when_no_text():
    # Blank pages have no extractable text — PII scan should yield no hits.
    meta = parse_pdf_metadata(_empty_pdf_bytes(pages=2), pii_scan_pages=2)
    assert meta.pii_warnings == []
