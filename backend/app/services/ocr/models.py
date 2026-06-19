from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LayoutRegion:
    region_id: str
    bbox: list[float]
    page_number: int
    region_type: str
    score: Optional[float] = None


@dataclass
class OcrRegion:
    region_id: str
    text: str
    bbox: list[float]
    page_number: int
    region_type: str
    confidence: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "text": self.text,
            "bbox": self.bbox,
            "page_number": self.page_number,
            "region_type": self.region_type,
            "confidence": self.confidence,
        }


@dataclass
class DocumentSegment:
    doc_type: str
    page_range: list[int]
    metadata: dict = field(default_factory=dict)
    content: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "page_range": self.page_range,
            "metadata": self.metadata,
            "content": self.content,
        }
