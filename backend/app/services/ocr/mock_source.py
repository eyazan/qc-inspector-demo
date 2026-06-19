"""
Mock OCR kaynagi — layout/OCR servisleri olmadan zinciri test etmek icin.

ocr_mode="mock" oldugunda devreye girer. Gercek bir vendor mill sertifikasinda
bulunabilecek gercekci bolgeler uretir: metin degerleri, bir tablo (structured_data
ile), ve bilerek dusuk guvenli (needs_review) bir bolge. Boylece compliance'in
tum dallari (deterministik eslesme, tablo parse, needs_review) test edilir.

NOT: Uretilen degerler ornek spec (data/specs/4500001234_10.md) ile uyumlu secildi:
  - Tensile 410 MPa  (spec min 380 -> PARTIAL, sinirda)
  - Yield 250 MPa    (spec min 280 -> NON_COMPLIANT)
  - Hardness 320 HB  (spec 250-380 -> COMPLIANT)
  - Carbon 0.18 %    (spec max 0.20 -> COMPLIANT)
"""

from app.services.ocr.models import OcrRegion


def build_mock_regions(page_count: int) -> list[OcrRegion]:
    """PDF sayfa sayisina gore sahte ama gercekci bolgeler uretir."""
    regions: list[OcrRegion] = []

    # Sayfa 1: baslik + mekanik ozellikler (metin)
    regions.append(OcrRegion(
        region_id="page1_region0", text="MILL TEST CERTIFICATE - EN 10204 3.1",
        bbox=[50, 40, 550, 70], page_number=1, region_type="doc_title", confidence=0.97,
    ))
    regions.append(OcrRegion(
        region_id="page1_region1",
        text="Tensile Strength: 410 MPa   Yield Strength: 250 MPa   Elongation: 22 %",
        bbox=[50, 90, 550, 130], page_number=1, region_type="text", confidence=0.94,
    ))

    # Sayfa 1: kimyasal bilesim (tablo, structured_data ile)
    regions.append(OcrRegion(
        region_id="page1_region2", text="Hardness 320 HB | Carbon 0.18 % | Manganese 1.20 %",
        bbox=[50, 150, 550, 250], page_number=1, region_type="table", confidence=0.91,
        structured_data={
            "format": "table",
            "header": ["Property", "Value"],
            "rows": [["Hardness", "320 HB"], ["Carbon", "0.18 %"], ["Manganese", "1.20 %"]],
            "row_count": 3, "col_count": 2,
        },
    ))

    # Bilerek dusuk guvenli bolge -> needs_review tetikler (kacirma yok ilkesi testi)
    regions.append(OcrRegion(
        region_id="page1_region3", text="[okunamayan damga / muhur]",
        bbox=[400, 600, 550, 700], page_number=1, region_type="seal", confidence=0.31,
        needs_review=True,
    ))

    # Kalan sayfalar icin jenerik metin bolgeleri (cok sayfali PDF testi)
    for page in range(2, page_count + 1):
        regions.append(OcrRegion(
            region_id=f"page{page}_region0",
            text=f"Devam sayfasi {page}: ek test sonuclari ve onay imzalari.",
            bbox=[50, 50, 550, 90], page_number=page, region_type="text", confidence=0.9,
        ))

    return regions
