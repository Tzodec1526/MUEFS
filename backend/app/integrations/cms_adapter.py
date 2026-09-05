"""CMS submission boundary. Only the demo has a simulated implementation."""

from dataclasses import dataclass

from app.config import settings


@dataclass
class CMSFilingResult:
    success: bool
    cms_case_number: str | None = None
    cms_filing_id: str | None = None
    error_message: str | None = None


async def submit_filing_to_cms(case_number: str, filing_id: int) -> CMSFilingResult:
    if not settings.allow_demo_mode:
        return CMSFilingResult(
            success=False, error_message="Court CMS integration is not configured",
        )
    return CMSFilingResult(
        success=True,
        cms_case_number=case_number,
        cms_filing_id=f"DEMO-{filing_id}",
    )
