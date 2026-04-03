"""Tests for document-related functionality."""


from app.services.document_service import (
    compute_sha256,
    validate_file_size,
    validate_mime_type,
)
from app.utils.pdf import check_pii_patterns, validate_electronic_signature


def test_compute_sha256():
    data = b"Hello, Michigan courts!"
    hash1 = compute_sha256(data)
    hash2 = compute_sha256(data)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest length


def test_compute_sha256_different_data():
    hash1 = compute_sha256(b"data1")
    hash2 = compute_sha256(b"data2")
    assert hash1 != hash2


def test_validate_file_size():
    # Default max is 100MB
    assert validate_file_size(1024) is True  # 1 KB
    assert validate_file_size(50 * 1024 * 1024) is True  # 50 MB
    assert validate_file_size(100 * 1024 * 1024) is True  # 100 MB exactly
    assert validate_file_size(101 * 1024 * 1024) is False  # 101 MB


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


def test_validate_electronic_signature():
    assert validate_electronic_signature("/s/ John Smith") is True
    assert validate_electronic_signature("Signed by John Smith") is False
    assert validate_electronic_signature("No signature here") is False
