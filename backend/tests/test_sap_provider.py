"""SAP Real/Mock provider selection + mock canned spec-code fallback."""

import app.providers.sap as sapmod
from app.providers.sap import MockSAPProvider, RealSAPProvider, get_sap_provider


def test_factory_mock_default(monkeypatch):
    monkeypatch.setattr(sapmod.settings, "active_sap_provider", "mock", raising=False)
    assert get_sap_provider().name == "mock"


def test_factory_real_requires_endpoint(monkeypatch):
    monkeypatch.setattr(sapmod.settings, "active_sap_provider", "real", raising=False)
    monkeypatch.setattr(sapmod.settings, "sap_spec_endpoint", "", raising=False)
    # no endpoint -> falls back to mock
    assert get_sap_provider().name == "mock"
    monkeypatch.setattr(sapmod.settings, "sap_spec_endpoint", "https://sap.local/x", raising=False)
    assert get_sap_provider().name == "real"


def test_factory_derives_from_spec_source(monkeypatch):
    monkeypatch.setattr(sapmod.settings, "active_sap_provider", "", raising=False)
    monkeypatch.setattr(sapmod.settings, "spec_source", "local", raising=False)
    assert get_sap_provider().name == "mock"


def test_mock_canned_spec_code_from_material(tmp_path, monkeypatch):
    # No local fixture -> mock derives spec code from material.
    monkeypatch.setattr(sapmod.settings, "spec_source_dir", tmp_path, raising=False)
    res = MockSAPProvider().fetch(material="AMS4911(20THK)B")
    assert res.status == "success"
    assert res.spec_name == "AMS4911"
