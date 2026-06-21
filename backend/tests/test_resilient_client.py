"""Resilient HTTP client: retries, failure exhaustion, circuit breaker.
Uses httpx.MockTransport (no real network/models)."""

import httpx
import pytest

import app.services.clients.http as http_mod
from app.services.clients.http import RemoteServiceError, post_json


def _mock_build_client(handler):
    def _factory(timeout_seconds, verify=None, cert=None):
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout_seconds)
    return _factory


def _reset_breakers():
    http_mod._breakers.clear()


def test_retries_then_succeeds(monkeypatch):
    _reset_breakers()
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"err": "busy"})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(http_mod, "build_client", _mock_build_client(handler))
    monkeypatch.setattr(http_mod.settings, "retry_backoff_seconds", 0.0, raising=False)
    out = post_json("http://svc.local/x", {"a": 1}, retries=3)
    assert out == {"ok": True}
    assert calls["n"] == 3  # 2 failures + 1 success


def test_exhausts_retries_raises(monkeypatch):
    _reset_breakers()

    def handler(request):
        return httpx.Response(500, json={"err": "down"})

    monkeypatch.setattr(http_mod, "build_client", _mock_build_client(handler))
    monkeypatch.setattr(http_mod.settings, "retry_backoff_seconds", 0.0, raising=False)
    with pytest.raises(RemoteServiceError):
        post_json("http://svc.local/x", {"a": 1}, retries=2)


def test_circuit_breaker_opens(monkeypatch):
    _reset_breakers()
    monkeypatch.setattr(http_mod.settings, "circuit_breaker_fail_max", 3, raising=False)
    monkeypatch.setattr(http_mod.settings, "circuit_breaker_reset_seconds", 999, raising=False)
    monkeypatch.setattr(http_mod.settings, "retry_backoff_seconds", 0.0, raising=False)

    def handler(request):
        return httpx.Response(500)

    monkeypatch.setattr(http_mod, "build_client", _mock_build_client(handler))
    # Drive failures past fail_max.
    for _ in range(3):
        with pytest.raises(RemoteServiceError):
            post_json("http://brk.local/x", {}, retries=0)
    # Next call should be refused by the open breaker (message says 'Circuit open').
    with pytest.raises(RemoteServiceError, match="Circuit open"):
        post_json("http://brk.local/x", {}, retries=0)
