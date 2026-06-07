"""Abstract CMS (Case Management System) integration interface.

Michigan courts use multiple CMS platforms:
- JIS (Judicial Information Services) - 80% of trial courts
- Tyler Odyssey - select courts
- Various legacy systems - ~60 courts

This adapter pattern allows the e-filing system to push accepted filings
to any court's CMS regardless of the underlying technology.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CMSFilingResult:
    success: bool
    cms_case_number: str | None = None
    cms_filing_id: str | None = None
    error_message: str | None = None


@dataclass
class CMSCaseInfo:
    case_number: str
    title: str
    status: str
    court_name: str
    filed_date: str
    parties: list[dict]


class CMSAdapter(ABC):
    """Base class for CMS integrations."""

    @abstractmethod
    async def submit_filing(
        self,
        case_number: str | None,
        case_title: str,
        documents: list[dict],
        parties: list[dict],
        filing_metadata: dict,
    ) -> CMSFilingResult:
        """Submit an accepted filing to the court's CMS."""
        ...

    @abstractmethod
    async def get_case(self, case_number: str) -> CMSCaseInfo | None:
        """Retrieve case information from the CMS."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the CMS integration is operational."""
        ...
