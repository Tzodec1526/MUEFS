"""Tyler Technologies Odyssey CMS adapter (Odyssey / TrueFiling courts).

Odyssey backs select Michigan courts, including the appellate TrueFiling system. Like the
JIS adapter, this is a stub for the MVP: it implements the CMSAdapter interface so the
platform can route accepted filings to an Odyssey court without changing call sites, but
it does not yet connect to a live Odyssey API.
"""

from app.integrations.cms_adapter import CMSAdapter, CMSCaseInfo, CMSFilingResult


class TylerOdysseyAdapter(CMSAdapter):
    """Adapter for Tyler Technologies' Odyssey / TrueFiling CMS."""

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
        # Stub: In production, this submits to the Tyler Odyssey / TrueFiling API.
        return CMSFilingResult(
            success=True,
            cms_case_number=case_number or "ODY-PENDING",
            cms_filing_id="ODYSSEY-STUB-001",
        )

    async def get_case(self, case_number: str) -> CMSCaseInfo | None:
        # Stub: In production, this queries Odyssey.
        return None

    async def health_check(self) -> bool:
        # Stub: In production, this pings Odyssey.
        return True
