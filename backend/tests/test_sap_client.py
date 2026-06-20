"""Mocked SAP client: build_client is patched so no live SAP call is made.
Verifies the request flow + Tdline parsing + spec-code extraction."""

import contextlib

import app.services.spec_sources.sap as sap_module
from app.services.spec_sources.sap import SapSpecSource


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "body": json, "headers": headers})
        return _FakeResponse(self._payload)


def _patch_build_client(monkeypatch, payload):
    client = _FakeClient(payload)

    @contextlib.contextmanager
    def fake_build_client(timeout):
        yield client

    monkeypatch.setattr(sap_module, "build_client", fake_build_client)
    return client


def test_sap_fetch_parses_tdlines_and_spec_code(monkeypatch):
    payload = {
        "Lines": {
            "item": [
                {"Tdline": "TITANIUM 6AL-4V SHEET"},
                {"Tdline": "MUST CONFORM TO AMS 4911 REV T"},
            ]
        }
    }
    _patch_build_client(monkeypatch, payload)
    monkeypatch.setattr(sap_module.settings, "sap_api_user", "u", raising=False)
    monkeypatch.setattr(sap_module.settings, "sap_api_password", "p", raising=False)

    result = SapSpecSource().fetch(po_number="4500180435", po_item="1")
    assert result.status == "success"
    assert "AMS 4911 REV T" in result.spec_text
    assert result.spec_name and result.spec_name.upper().replace(" ", "") == "AMS4911"


def test_sap_fetch_not_found_on_empty(monkeypatch):
    _patch_build_client(monkeypatch, {"Lines": {"item": []}})
    result = SapSpecSource().fetch(po_number="999", po_item="1")
    assert result.status == "not_found"


def test_sap_basic_auth_header_present(monkeypatch):
    client = _patch_build_client(monkeypatch, {"Lines": {"item": [{"Tdline": "AMS 4911"}]}})
    monkeypatch.setattr(sap_module.settings, "sap_api_user", "u", raising=False)
    monkeypatch.setattr(sap_module.settings, "sap_api_password", "p", raising=False)
    SapSpecSource().fetch(po_number="4500180435", po_item="1")
    assert client.calls
    assert client.calls[0]["headers"]["Authorization"].startswith("Basic ")
