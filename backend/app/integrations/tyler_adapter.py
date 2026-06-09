"""Tyler Technologies Odyssey CMS adapter (Odyssey / TrueFiling courts).

Odyssey backs select Michigan courts, including the appellate TrueFiling system. Like the
JIS adapter, this is a **stub** for the MVP: it implements the ``CMSAdapter`` interface so the
platform can route accepted filings to an Odyssey court without changing any call sites, but
it does **not** connect to a live Odyssey API.

Document-type mapping (not yet implemented)
-------------------------------------------
A production implementation would translate MUEFS's MCR-based document-type codes (e.g.
``COMPLAINT``, ``MOT_SD``, ``BRIEF_SUPPORT`` — see the document catalog in
``frontend/src/components/filing/DocumentUpload.tsx``) into the target court's Odyssey
filing-code taxonomy. Tyler deployments typically expose
those codes through an Electronic Filing Manager (EFM) "code list"/policy service per court,
and accept filings via the OASIS LegalXML ECF 4.0 envelope. The mapping is therefore
court-specific and should be loaded from the court's published code list rather than
hard-coded here — so this stub intentionally does not fabricate it.
"""

from app.integrations.cms_adapter import CMSAdapter, CMSCaseInfo, CMSFilingResult


class TylerOdysseyAdapter(CMSAdapter):
    """Adapter for Tyler Technologies' Odyssey / TrueFiling CMS (stub)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url
        self.api_key = api_key

    async def submit_filing(
        self,
        case_number: str | None,
        case_title: str,
        documents: list[dict],
        parties: list[dict],
        filing_metadata: dict,
    ) -> CMSFilingResult:
        """Submit an accepted filing to the court's Odyssey instance.

        Production: build an ECF 4.0 filing envelope (mapping each document's MUEFS
        document-type code to the court's Odyssey filing code), submit it via the court's
        EFM endpoint, and return the Odyssey case/filing identifiers or an error. This stub
        returns a placeholder success without contacting any system.
        """
        return CMSFilingResult(
            success=True,
            cms_case_number=case_number or "ODY-PENDING",
            cms_filing_id="ODYSSEY-STUB-001",
        )

    async def get_case(self, case_number: str) -> CMSCaseInfo | None:
        """Look up a case in Odyssey by case number.

        Production: query the EFM/Odyssey case service and map the response onto
        ``CMSCaseInfo``. This stub always returns ``None`` (no live connection).
        """
        return None

    async def health_check(self) -> bool:
        """Report whether the Odyssey integration is reachable.

        Production: ping the EFM endpoint and validate credentials. This stub always
        returns ``True``.
        """
        return True
