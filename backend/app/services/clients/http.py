"""Resilient HTTP client for remote model services (OCR, LLM).

Production concerns handled here so providers stay thin:
  - per-call timeout (config REQUEST_TIMEOUT / explicit)
  - retries with exponential backoff on transient errors (5xx, timeouts, conn)
  - a simple per-host circuit breaker (open after N consecutive failures)
  - TLS / mTLS via config
  - structured logging that NEVER logs Authorization tokens or payload bodies
"""

import threading
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def build_client(timeout_seconds: int, verify=None, cert=None) -> httpx.Client:
    """HTTP client with per-call TLS. `verify` is a CA-bundle path, True, or
    False (per-service from config); defaults to the global TLS option.

    `cert` is the client (mTLS) certificate; when None NO client cert is sent.
    The global mTLS cert is NOT auto-attached here so that callers which must
    reach an endpoint WITHOUT a client cert (e.g. the SAP spec service) can do
    so. Callers that need mTLS pass `cert` explicitly (post_json does this for
    the OCR/LLM services)."""
    return httpx.Client(
        timeout=httpx.Timeout(float(timeout_seconds)),
        verify=settings.tls_verify_option if verify is None else verify,
        cert=cert,
    )


@dataclass
class _Breaker:
    fail_max: int
    reset_seconds: float
    failures: int = 0
    opened_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self) -> bool:
        with self.lock:
            if self.failures < self.fail_max:
                return True
            # Open: allow a trial request once the reset window passes (half-open).
            if time.monotonic() - self.opened_at >= self.reset_seconds:
                return True
            return False

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.opened_at = 0.0

    def record_failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= self.fail_max and self.opened_at == 0.0:
                self.opened_at = time.monotonic()


_breakers: dict[str, _Breaker] = {}
_breakers_lock = threading.Lock()


def _breaker_for(host: str) -> _Breaker:
    with _breakers_lock:
        b = _breakers.get(host)
        if b is None:
            b = _Breaker(
                fail_max=settings.circuit_breaker_fail_max,
                reset_seconds=float(settings.circuit_breaker_reset_seconds),
            )
            _breakers[host] = b
        return b


class RemoteServiceError(Exception):
    """Raised when a remote model service call ultimately fails."""


def post_json(
    url: str,
    payload: dict,
    headers: dict | None = None,
    timeout_seconds: int | None = None,
    retries: int | None = None,
    verify=None,
    cert=None,
) -> dict:
    """POST JSON with retries + circuit breaker. Returns parsed JSON.

    Tokens in `headers` are sent but never logged.
    """
    timeout = timeout_seconds if timeout_seconds is not None else settings.request_timeout_seconds
    max_retries = retries if retries is not None else settings.retry_count
    backoff = settings.retry_backoff_seconds
    host = httpx.URL(url).host or url
    breaker = _breaker_for(host)

    if not breaker.allow():
        raise RemoteServiceError(f"Circuit open for {host}; not sending request")

    # OCR/LLM internal services use the global mTLS client cert by default;
    # callers can override with an explicit cert. (SAP calls build_client
    # directly without a cert, so it never sends one.)
    effective_cert = cert if cert is not None else settings.llm_tls_cert

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with build_client(timeout, verify=verify, cert=effective_cert) as client:
                resp = client.post(url, json=payload, headers=headers or {})
            if resp.status_code in _RETRYABLE_STATUS:
                raise httpx.HTTPStatusError(
                    f"retryable {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            breaker.record_success()
            return resp.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as err:
            last_err = err
            breaker.record_failure()
            status = getattr(getattr(err, "response", None), "status_code", "conn")
            if attempt < max_retries:
                sleep_s = backoff * (2 ** attempt)
                logger.warning(
                    "Remote call %s failed (%s), retry %s/%s in %.1fs",
                    host, status, attempt + 1, max_retries, sleep_s,
                )
                time.sleep(sleep_s)
            else:
                logger.error("Remote call %s exhausted retries (%s)", host, status)
        except Exception as err:  # noqa: BLE001
            last_err = err
            breaker.record_failure()
            logger.error("Remote call %s unexpected error: %s", host, type(err).__name__)
            break

    raise RemoteServiceError(f"Remote service {host} call failed: {last_err}") from last_err
