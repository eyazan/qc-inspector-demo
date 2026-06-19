"""Spec lookup strategy interface (Section 3).

The vendor pipeline asks for a spec and the strategy chains its sources. The
result carries the resolved spec text + sections for comparison, or a structured
error (stage 'spec_lookup' / 'sap_spec_fetch') — never a bare exception.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpecLookupResult:
    status: str                       # found | not_found | error
    source: Optional[str] = None      # sap_text | local_store_exact | fuzzy | freshly_indexed
    spec_no: Optional[str] = None
    spec_text: str = ""
    sections: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    file_path: Optional[str] = None
    stage: Optional[str] = None       # set on error
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "spec_no": self.spec_no,
            "spec_text": self.spec_text,
            "sections": self.sections,
            "references": self.references,
            "file_path": self.file_path,
            "stage": self.stage,
            "message": self.message,
        }


class SpecLookupStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def resolve(
        self,
        po_number: str | None = None,
        po_item: str | None = None,
        material: str | None = None,
        extra_specs: list[str] | None = None,
    ) -> SpecLookupResult:
        ...
