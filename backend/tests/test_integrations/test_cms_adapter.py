from app.config import settings
from app.integrations.cms_adapter import submit_filing_to_cms


async def test_cms_records_only_outside_demo_and_simulates_inside(monkeypatch):
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    result = await submit_filing_to_cms("CASE-1", 12)
    assert result.success is True
    assert result.cms_filing_id is None
    assert result.cms_case_number == "CASE-1"
    assert result.error_message is None

    monkeypatch.setattr(settings, "allow_demo_mode", True)
    first = await submit_filing_to_cms("CASE-1", 12)
    second = await submit_filing_to_cms("CASE-1", 13)
    assert first.success and second.success
    assert first.cms_case_number == "CASE-1"
    assert first.cms_filing_id == "DEMO-12"
    assert second.cms_filing_id == "DEMO-13"
