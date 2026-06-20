"""SAP spec provider: Real vs Mock, configuration-selected.

No SAP-specific logic lives in business services — they call get_sap_provider()
which returns a SpecSource. RealSAPProvider hits the SAP endpoint; MockSAPProvider
serves local fixtures + a canned spec-code fallback so dev/test works with no SAP
access. Selected by ACTIVE_SAP_PROVIDER (real|mock); if unset, derived from the
legacy SPEC_SOURCE (sap->real, local->mock).
"""

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.services.spec_sources.base import SpecResult, SpecSource
from app.services.spec_sources.local import LocalSpecSource
from app.services.spec_sources.sap import SapSpecSource

logger = get_logger(__name__)

_SPEC_CODE = re.compile(r"\b(AMS\s?\d{3,5}[A-Z]?|ABS\s?\d{3,5}[A-Z]?|S-\d{2,5}[A-Z]?)\b", re.I)


class RealSAPProvider(SapSpecSource):
    name = "real"


class MockSAPProvider(LocalSpecSource):
    """Local fixtures first; then a canned spec-code derived from material/PO so
    the downstream lookup chain has something to resolve without a real SAP."""

    name = "mock"

    def fetch(self, po_number=None, po_item=None, material=None) -> SpecResult:
        result = super().fetch(po_number=po_number, po_item=po_item, material=material)
        if result.status == "success":
            return result
        code = ""
        m = _SPEC_CODE.search(material or "")
        if m:
            code = re.sub(r"\s+", "", m.group(1))
        if code:
            logger.info("MockSAP: canned spec_name '%s' from material", code)
            return SpecResult(status="success", spec_name=code, spec_text="", lines=[])
        return SpecResult(status="not_found")


def get_sap_provider() -> SpecSource:
    choice = (settings.active_sap_provider or "").lower()
    if not choice:
        choice = "real" if settings.spec_source == "sap" else "mock"
    if choice == "real" and settings.sap_spec_endpoint:
        return RealSAPProvider()
    if choice == "real":
        logger.warning("SAP provider 'real' selected but no endpoint; falling back to mock")
    return MockSAPProvider()
