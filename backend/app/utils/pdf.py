"""PDF utilities for MCR 1.109 compliance."""

import re


def check_pii_patterns(text: str) -> list[str]:
    """Check for potential PII that should be redacted per MCR 1.109."""
    warnings = []

    # SSN pattern: XXX-XX-XXXX
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
        warnings.append(
            "Possible Social Security Number detected. "
            "MCR 1.109 requires SSN redaction."
        )

    # Date of birth patterns
    if re.search(r"\b(?:DOB|Date of Birth|Birth Date)\s*[:]\s*\d", text, re.IGNORECASE):
        warnings.append(
            "Possible date of birth detected. "
            "MCR 1.109 requires DOB redaction (show only year if needed)."
        )

    # Driver's license
    if re.search(r"\b(?:DL|Driver'?s?\s*License)\s*#?\s*[:]\s*\w", text, re.IGNORECASE):
        warnings.append(
            "Possible driver's license number detected. "
            "MCR 1.109 requires DL number redaction."
        )

    # Financial account numbers (long digit sequences)
    if re.search(r"\b\d{12,19}\b", text):
        warnings.append(
            "Possible financial account number detected. "
            "MCR 1.109 requires financial account number redaction."
        )

    return warnings


def validate_electronic_signature(text: str) -> bool:
    """Check if document contains valid electronic signature format per MCR 1.109."""
    return bool(re.search(r"/s/\s+\w", text))
