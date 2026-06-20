from app.services.spec_sources.base import SpecResult, SpecSource


def get_spec_source() -> SpecSource:
    """Backward-compatible accessor; delegates to the SAP provider factory
    (Real/Mock selected by ACTIVE_SAP_PROVIDER, else derived from SPEC_SOURCE)."""
    from app.providers.sap import get_sap_provider

    return get_sap_provider()
