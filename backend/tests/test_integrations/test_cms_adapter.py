"""Tests for CMS adapter interface."""

import pytest

from app.integrations.jis_adapter import JISAdapter


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
