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
