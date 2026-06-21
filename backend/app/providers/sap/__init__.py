"""SAP spec provider — REAL service, configuration-driven. No mock/fabricated
data: business services call get_sap_provider() which returns a SpecSource.

- RealSAPProvider hits the configured SAP/spec-lookup service (URL + bearer/basic
  + per-service CA bundle), looking up by PO number, PO item, material, or spec.
- When no SAP endpoint is configured (local dev), fall back to LocalSpecSource,
  which reads REAL spec text files placed under SPEC_SOURCE_DIR. It never invents
  a spec; if nothing matches it returns not_found, and the lookup chain then
  resolves via the LLM-extracted spec references against the indexed spec store.

Selected by ACTIVE_SAP_PROVIDER (real|local); if unset, derived from whether a
SAP endpoint is configured.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.services.spec_sources.base import SpecSource
from app.services.spec_sources.local import LocalSpecSource
from app.services.spec_sources.sap import SapSpecSource

logger = get_logger(__name__)


class RealSAPProvider(SapSpecSource):
    name = "real"


def get_sap_provider() -> SpecSource:
    choice = (settings.active_sap_provider or "").lower()
    if not choice:
        choice = "real" if settings.sap_spec_endpoint else "local"
    if choice == "real" and settings.sap_spec_endpoint:
        return RealSAPProvider()
    if choice == "real":
        logger.warning("SAP provider 'real' selected but no endpoint; using local spec files")
    return LocalSpecSource()
