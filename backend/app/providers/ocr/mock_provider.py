"""Mock OCR provider — no remote call.

Returns canned vendor-document text so the offline smoke test exercises PO/spec
extraction, segmentation and comparison without a live OCR host. The text
mirrors the real sample documents (receiving report + spec callouts).
"""

from app.providers.ocr.base import OcrProvider

_MOCK_TEXT = (
    "Mal giris fisi / Receiving Report\n"
    "Purchase Order / SA siparisi 4500180435\n"
    "Sira PO Kalem Malzeme\n"
    "1 4500180435 00001 AMS4911(20THK)B\n"
    "Material: AMS4911(20THK)B REV R OR LATER\n"
    "Titanium 6Al-4V Annealed Sheet\n"
    "Heat No: H12345  Lot: L678\n"
    "Specs: AMS4911S, AIMS 03-18-001, ABS 5125A, DIN 65039, ASTM B265\n"
    "Ti balance Al 6.10 V 4.05 Fe 0.18 Si 0.03 C 0.02 N 0.01 H 0.003 O 0.13\n"
    "Tensile Strength 950 MPa  Yield Strength 880 MPa  Elongation 12 %\n"
)


class MockOcrProvider(OcrProvider):
    name = "mock"

    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        return _MOCK_TEXT, 0.99
