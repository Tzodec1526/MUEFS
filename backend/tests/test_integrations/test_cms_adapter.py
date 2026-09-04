"""Tests for CMS adapter interface."""

from app.integrations.cms_adapter import get_cms_adapter
from app.integrations.jis_adapter import JISAdapter
from app.integrations.tyler_adapter import TylerOdysseyAdapter


def test_get_cms_adapter_selects_by_cms_type():
    assert isinstance(get_cms_adapter("JIS"), JISAdapter)
    assert isinstance(get_cms_adapter("TrueFiling"), TylerOdysseyAdapter)
    assert isinstance(get_cms_adapter("Tyler Odyssey"), TylerOdysseyAdapter)
    assert isinstance(get_cms_adapter(None), JISAdapter)
