"""Tests for CMS adapter interface."""

import pytest

from app.integrations.cms_adapter import get_cms_adapter
from app.integrations.jis_adapter import JISAdapter
from app.integrations.tyler_adapter import TylerOdysseyAdapter


@pytest.mark.asyncio
async def test_jis_adapter_submit():
    adapter = JISAdapter()
    result = await adapter.submit_filing(
        case_number="MI-3-2024-000001",
        case_title="Smith v. Jones",
        documents=[{"title": "Complaint", "type": "COMPLAINT"}],
        parties=[{"name": "John Smith", "role": "plaintiff"}],
        filing_metadata={"court_id": 1},
    )
    assert result.success is True
    assert result.cms_case_number is not None


@pytest.mark.asyncio
async def test_jis_adapter_health_check():
    adapter = JISAdapter()
    assert await adapter.health_check() is True


@pytest.mark.asyncio
async def test_jis_adapter_get_case():
    adapter = JISAdapter()
    result = await adapter.get_case("NONEXISTENT-001")
    assert result is None  # Stub returns None


def test_get_cms_adapter_selects_by_cms_type():
    assert isinstance(get_cms_adapter("JIS"), JISAdapter)
    assert isinstance(get_cms_adapter("TrueFiling"), TylerOdysseyAdapter)
    assert isinstance(get_cms_adapter("Tyler Odyssey"), TylerOdysseyAdapter)
    assert isinstance(get_cms_adapter(None), JISAdapter)


@pytest.mark.asyncio
async def test_tyler_adapter_submit():
    adapter = TylerOdysseyAdapter()
    result = await adapter.submit_filing(
        case_number=None,
        case_title="Doe v. Roe",
        documents=[],
        parties=[],
        filing_metadata={},
    )
    assert result.success is True
    assert result.cms_filing_id == "ODYSSEY-STUB-001"
