import httpx

from app.core.config import settings


def build_client(timeout_seconds: int) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(float(timeout_seconds)),
        verify=settings.tls_verify_option,
        cert=settings.llm_tls_cert,
    )
