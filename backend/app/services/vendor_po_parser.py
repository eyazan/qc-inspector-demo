"""
Vendor ilk sayfasindan (tesellum/mal giris fisi) PO / kalem / malzeme cikarir.

ETIKET-BAZLI: OCR rakamlari tek tek boslukla basabilir ("4 5 0 0" = 4500),
bu yuzden bilinen etiketten ("Purchase Order", "Kalem"...) sonraki rakamlar
bosluklari atilarak okunur. Hicbir deger hardcoded degil; sadece etiket desenleri.

ONEMLI ayrim:
  "Receiving Report No / Mal giris fisi" -> FIS NO (PO DEGIL)
  "Purchase Order / SA siparisi"          -> GERCEK PO
"""
import re
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VendorIds:
    po_number: str | None = None
    po_item: str | None = None
    material: str | None = None


def _collapse_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _digits_after_label(text: str, label_pattern: str, max_window: int = 60) -> str:
    pat = re.compile(
        label_pattern + r"\s*:?\s*([0-9][0-9\s]{0," + str(max_window) + r"})",
        re.IGNORECASE,
    )
    m = pat.search(text)
    return _collapse_digits(m.group(1)) if m else ""


_MATERIAL = re.compile(r"\b([A-Z]{2,}[A-Z0-9]*\s*\([^)]+\)\s*[A-Z0-9]*)", re.IGNORECASE)


def parse_vendor_ids(first_page_text: str, file_name: str = "") -> VendorIds:
    text = first_page_text or ""
    po_number = po_item = material = None

    # 1) PO — "Purchase Order / SA siparisi" etiketinden (fis no DEGIL)
    po = _digits_after_label(text, r"(?:SA\s*sipari[sş]i\s*/?\s*)?Purchase\s*Order")
    if not po:
        po = _digits_after_label(text, r"Sat[ıi]n\s*Alma\s*Sipari[sş]i")
    if po:
        po_number = po
        logger.info("Vendor PO bulundu (Purchase Order etiketi): %s", po_number)

    # 2) Kalem (item) — "Sira PO Kalem ..." tablosundan
    item = _extract_item(text, po_number)
    if item:
        po_item = item
        logger.info("Vendor kalem bulundu: %s", po_item)

    # 3) Malzeme
    mm = _MATERIAL.search(text)
    if mm:
        material = mm.group(1).strip()
        logger.info("Vendor malzeme bulundu (metin): %s", material)

    # 4) Fallback — dosya adindan
    if not po_number and file_name:
        mfile = re.search(r"\b(\d{10})\b", file_name)
        if mfile:
            po_number = mfile.group(1)
            logger.info("Vendor PO dosya adindan alindi (fallback): %s", po_number)
    if not material and file_name:
        mm2 = _MATERIAL.search(file_name)
        if mm2:
            material = mm2.group(1).strip()
            logger.info("Vendor malzeme dosya adindan alindi (fallback): %s", material)

    if not (po_number or po_item or material):
        logger.warning("Vendor ilk sayfasindan PO/kalem/malzeme cikarilamadi")
    return VendorIds(po_number=po_number, po_item=po_item, material=material)


def _extract_item(text: str, po_number: str | None) -> str | None:
    head = re.search(r"PO\s*Kalem[^\n]*\n(.*)", text, re.IGNORECASE | re.DOTALL)
    region = head.group(1) if head else text
    m = re.search(
        r"([0-9][0-9\s]{2,6}?)\s{2,}([0-9][0-9\s]{16,28}?)\s{2,}([0-9][0-9\s]{8,12})",
        region,
    )
    if m:
        item = _collapse_digits(m.group(3))
        if 4 <= len(item) <= 6:
            return item
    if po_number:
        spaced = r"\s*".join(list(po_number))
        m2 = re.search(spaced + r"\s+([0-9](?:\s*[0-9]){4})\b", text)
        if m2:
            item = _collapse_digits(m2.group(1))
            if len(item) == 5:
                return item
    return None
