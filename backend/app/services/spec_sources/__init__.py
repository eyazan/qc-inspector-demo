from app.core.config import settings
from app.services.spec_sources.base import SpecResult, SpecSource
from app.services.spec_sources.local import LocalSpecSource
from app.services.spec_sources.sap import SapSpecSource


def get_spec_source() -> SpecSource:
    """config.spec_source -> 'sap' | 'local'. sap secilip endpoint bossa local'e duser."""
    if settings.spec_source == "sap" and settings.sap_spec_endpoint:
        return SapSpecSource()
    return LocalSpecSource()
