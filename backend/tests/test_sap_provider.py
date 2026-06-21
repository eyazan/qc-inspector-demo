"""SAP provider selection — real service vs real local-file source. No mock data."""

import app.providers.sap as sapmod
from app.providers.sap import RealSAPProvider, get_sap_provider
from app.services.spec_sources.local import LocalSpecSource


def test_real_when_endpoint_configured(monkeypatch):
    monkeypatch.setattr(sapmod.settings, "active_sap_provider", "real", raising=False)
    monkeypatch.setattr(sapmod.settings, "sap_spec_endpoint", "https://sap.internal/x", raising=False)
    assert isinstance(get_sap_provider(), RealSAPProvider)


def test_local_when_no_endpoint(monkeypatch):
    monkeypatch.setattr(sapmod.settings, "active_sap_provider", "", raising=False)
    monkeypatch.setattr(sapmod.settings, "sap_spec_endpoint", "", raising=False)
    assert isinstance(get_sap_provider(), LocalSpecSource)


def test_local_source_returns_not_found_without_fixture(tmp_path, monkeypatch):
    # Honest: no fabricated spec — returns not_found when no local file matches.
    monkeypatch.setattr(sapmod.settings, "spec_source_dir", tmp_path, raising=False)
    res = LocalSpecSource().fetch(material="AMS4911(20THK)B")
    assert res.status == "not_found"
