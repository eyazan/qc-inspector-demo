from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpecResult:
    status: str                      # "success" | "not_found" | "error"
    spec_name: Optional[str] = None  # spec numarasi/adi (SAP'tan)
    spec_text: str = ""              # spec metni (satirlar birlestirilmis)
    header: Optional[str] = None
    lines: list[str] = field(default_factory=list)


class SpecSource(ABC):
    @abstractmethod
    def fetch(self, po_number=None, po_item=None, material=None) -> SpecResult:
        ...
