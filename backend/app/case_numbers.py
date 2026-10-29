"""Case-number suffixes for the demo's filing catalog.

The catalog groups some subjects more broadly than SCAO's case types. These are
representative classifications, not a substitute for a court's CMS assigning the
official number; without a connected CMS, acceptance records these numbers.
Already assigned numbers are never reformatted.
SCAO source:
https://courts.mi.gov/siteassets/court-administration/standardsguidelines/casefile/cf_casetypecodes.pdf
"""

from app.models.court import CourtType

_CASE_CODES = {
    "CIV-GEN": "CZ",
    "CIV-TORT": "NO",
    "CIV-CONT": "CK",
    "CIV-PROP": "CH",
    "CIV-COND": "CC",
    "CIV-BUS": "CB",
    "CIV-GARN": "PS",
    "CIR-APP": "AV",
    "CIV-SUBP": "PZ",
    "LT-SP": "LT",
    "SM-CLM": "SC",
    "FAM-DIV": "DM",
    "FAM-CUST": "DC",
    "FAM-SUP": "DS",
    "FAM-PPO": "PP",
    "FAM-ADPT": "AD",
    "CR-FEL": "FH",
    "CR-MISD": "SM",
    "TR-CIV": "SI",
    "PR-EST": "DE",
    "PR-GRDN": "GA",
    "PR-CNSRV": "CA",
    "PR-TRUST": "TT",
    "PR-MI": "MI",
    "COC-TORT": "MZ",
    "COC-CONT": "MK",
    "COC-CONST": "MM",
    "COC-TAX": "MT",
    "COC-HWY": "MD",
    "COC-PROP": "MZ",
    "COC-APPREV": "MZ",
    # Appellate demo entries use representative subject codes, too; live appellate
    # courts assign their own identifiers through their CMS.
    "APP-CIV": "AV",
    "APP-CR": "AR",
    "APP-FAM": "AV",
}

_DISTRICT_CASE_CODES = {
    "CIV-GEN": "GC",
    "CIV-TORT": "GC",
    "CIV-CONT": "GC",
    "CIV-PROP": "GZ",
    "CIV-GARN": "GZ",
    "CIV-SUBP": "GZ",
    "CR-FEL": "FY",
}


def case_number_code(court_type: CourtType, code: str) -> str:
    """Translate catalog identifiers; preserve an explicitly configured case code."""
    if court_type in (CourtType.DISTRICT, CourtType.MUNICIPAL):
        return _DISTRICT_CASE_CODES.get(code, _CASE_CODES.get(code, code))
    return _CASE_CODES.get(code, code)
