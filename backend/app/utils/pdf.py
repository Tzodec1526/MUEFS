import re


def check_pii_patterns(text: str) -> list[str]:
    warnings = []

    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
        warnings.append(
            "Possible Social Security number detected. "
            "MCR 1.109 requires Social Security number redaction."
        )

    if re.search(r"\b(?:DOB|Date of Birth|Birth Date)\s*[:]\s*\d", text, re.IGNORECASE):
        warnings.append(
            "Possible date of birth detected. "
            "MCR 1.109 requires date of birth redaction (show only the year if needed)."
        )

    if re.search(r"\b(?:DL|Driver'?s?\s*License)\s*#?\s*[:]\s*\w", text, re.IGNORECASE):
        warnings.append(
            "Possible driver's license number detected. "
            "MCR 1.109 requires driver's license number redaction."
        )

    if re.search(r"\b\d{12,19}\b", text):
        warnings.append(
            "Possible financial account number detected. "
            "MCR 1.109 requires financial account number redaction."
        )

    return warnings
