"""Observability: request metrics increment + /metrics + readiness shape."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_increment():
    client.get("/health")
    snap = client.get("/metrics").json()
    assert snap["counters"].get("http_requests_total", 0) >= 1


def test_metrics_prometheus_text():
    client.get("/health")
    text = client.get("/metrics/prometheus").text
    assert "qc_http_requests_total" in text


def test_readiness_shape():
    body = client.get("/health/ready").json()
    assert "status" in body and "checks" in body
    assert set(body["checks"]) == {"layout", "ocr", "llm"}


def test_request_id_header():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_system_config_non_secret():
    """System Health screen feed: provider/endpoint summary, never secrets."""
    body = client.get("/api/system/config").json()
    assert set(body) >= {"app", "environment", "providers", "endpoints", "spec_indexing", "performance"}
    assert {"layout", "ocr", "llm", "sap", "spec_store"} <= set(body["providers"])
    # No secret-looking keys must leak.
    flat = str(body).lower()
    for leaked in ("bearer", "token", "password", "secret", "api_key"):
        assert leaked not in flat


def test_specs_list_shape():
    body = client.get("/api/specs").json()
    assert "count" in body and "results" in body
    assert isinstance(body["results"], list)
    if body["results"]:
        assert {"spec_no", "status"} <= set(body["results"][0])
