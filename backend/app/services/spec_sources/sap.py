"""
SAP spec kaynagi — gercek SAP /read-text servisine gore (SpecQueryService referans).

Bu QC Inspector akisinda SAP'tan TEK ihtiyacimiz:
  - spec_text : Lines.item[].Tdline satirlarinin birlesimi (karsilastirma icin)
  - spec_name : metinden cikarilan spec kodu (S-SPEC / TEI SPECIFICATION ...) —
                network'te spec PDF bulmak icin (spec_finder)

NOT: Tam SpecData (mekanik/kimyasal/tolerans) parse'i burada YAPILMAZ; o senin
ayri SpecQueryService'inin isi. Burada sadece metin + spec kodu uretilir.

Sorgu onceligi: 1) PO+item  2) malzeme (IMatnr)  3) PO-only
Her birinde Language T -> E fallback. Body ve parse SAP servisinle birebir.
"""
import base64
import json
import re

from app.core.config import settings
from app.core.logging import get_logger
from app.services.clients.http import build_client
from app.services.spec_sources.base import SpecResult, SpecSource
from app.services.vendor_po_parser import zero_pad_item

logger = get_logger(__name__)


class SapSpecSource(SpecSource):
    def __init__(self):
        # settings.sap_spec_endpoint = PO_API_BASE_URL (ornek .../erp-mm/part-spec)
        self._base_url = settings.sap_spec_endpoint.rstrip("/")
        self._url = self._base_url + settings.sap_spec_read_path  # /read-text
        self._timeout = settings.sap_spec_timeout_seconds
        self._user = settings.sap_api_user
        self._password = settings.sap_api_password

    # ---------------- public ----------------
    def fetch(self, po_number=None, po_item=None, material=None) -> SpecResult:
        po_number = (po_number or "").strip()
        po_item = (po_item or "").strip()
        material = (material or "").strip()

        # 1) PO + item
        if po_number and po_item:
            r = self._query_po(po_number, zero_pad_item(po_item))
            if r.status == "success":
                return r
        # 2) Malzeme (IMatnr)
        if material:
            r = self._query_material(material)
            if r.status == "success":
                return r
        # 3) PO-only (item zorunlu degilse ISasno ile dene)
        if po_number and not po_item:
            r = self._query_po(po_number, "")
            if r.status == "success":
                return r
        return SpecResult(status="not_found")

    # ---------------- SAP istekleri ----------------
    def _query_po(self, po_number: str, item_padded: str) -> SpecResult:
        for lang in ("T", "E"):
            body = {
                "ArchiveHandle": "",
                "Client": "",
                "IItemno": item_padded,
                "IMatnr": "",
                "ISasno": po_number,
                "Language": lang,
                "Lines": {"item": {"Tdformat": {}, "Tdline": {}}},
                "Name": {},
                "Object": {},
            }
            raw = self._post(body, f"PO={po_number} item={item_padded} lang={lang}")
            if raw is not None:
                result = self._parse(raw, hint_material="")
                if result.status == "success" and result.spec_text.strip():
                    return result
        return SpecResult(status="not_found")

    def _query_material(self, imatnr: str) -> SpecResult:
        for lang in ("T", "E"):
            body = {
                "ArchiveHandle": "",
                "Client": "",
                "IItemno": "",
                "IMatnr": imatnr,
                "ISasno": "",
                "Language": lang,
                "Lines": {"item": {"Tdformat": {}, "Tdline": {}}},
                "Name": {},
                "Object": {},
            }
            raw = self._post(body, f"IMatnr={imatnr} lang={lang}")
            if raw is not None:
                result = self._parse(raw, hint_material=imatnr)
                if result.status == "success" and result.spec_text.strip():
                    return result
        return SpecResult(status="not_found")

    def _auth_header(self) -> str:
        """Bearer token if configured (SAP_SPEC_SERVICE_BEARER_TOKEN), else Basic."""
        if settings.sap_spec_service_bearer_token:
            return f"Bearer {settings.sap_spec_service_bearer_token}"
        token = base64.b64encode(
            f"{self._user}:{self._password}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    def _post(self, body: dict, ctx: str) -> dict | None:
        """SAP'a POST. Per-service TLS (SAP_SPEC_SERVICE_CA_BUNDLE/VERIFY_TLS)."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self._auth_header(),
        }
        logger.info("SAP istek | url=%s | %s", self._url, ctx)
        try:
            with build_client(self._timeout, verify=settings.sap_tls_verify) as client:
                response = client.post(self._url, json=body, headers=headers)
        except Exception as err:  # noqa: BLE001
            logger.error("SAP baglanti/istek hatasi (%s): %s", ctx, err)
            return None

        status = response.status_code
        logger.info("SAP yanit | status=%s | %s", status, ctx)
        if status in (401, 403, 404) or 500 <= status < 600:
            logger.warning("SAP HTTP %s (%s)", status, ctx)
            return None
        try:
            response.raise_for_status()
            return response.json()
        except Exception as err:  # noqa: BLE001
            logger.warning("SAP yanit JSON/durum hatasi (%s): %s", ctx, err)
            return None

    # ---------------- parse (SAP servisinle ayni) ----------------
    def _parse(self, raw: dict, hint_material: str = "") -> SpecResult:
        # Lines.item[].Tdline topla
        lines_data = raw.get("Lines", {})
        items = []
        if isinstance(lines_data, dict):
            items = lines_data.get("item", [])
        elif isinstance(lines_data, list):
            for entry in lines_data:
                if isinstance(entry, dict) and "item" in entry:
                    iv = entry["item"]
                    if isinstance(iv, list):
                        items.extend(iv)
                    elif isinstance(iv, dict):
                        items.append(iv)
        if isinstance(items, dict):
            items = [items]
        if not items:
            return SpecResult(status="not_found")

        text_lines = []
        for item in items:
            tdline = item.get("Tdline", "") if isinstance(item, dict) else ""
            if isinstance(tdline, str) and tdline.strip():
                text_lines.append(tdline.strip())
        full_text = "\n".join(text_lines)
        if not full_text.strip():
            return SpecResult(status="not_found")

        spec_name = self._extract_spec_code(full_text) or self._material_to_spec(hint_material)
        logger.info(
            "SAP spec text alindi | satir=%s | karakter=%s | spec_code=%s",
            len(text_lines), len(full_text), spec_name or "(yok)",
        )
        return SpecResult(
            status="success",
            spec_name=spec_name or None,
            spec_text=full_text,
            lines=text_lines,
        )

    def _extract_spec_code(self, text: str) -> str:
        """SAP metninden spec kodu cikar (SpecQueryService ile ayni desenler)."""
        m = re.search(r"S-SPEC\s+(S-\d+[A-Z]?)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"GEAE\s+S-SPEC\s+(S-\d+[A-Z]?)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(
            r"S-SPEC[ \t]+([^\r\n]+?)(?:\s{2,}|\t|\r|\n|$|"
            r"\s+(?:REVISION|OR\s+LATER|REQUIREMENT|MUST\s+CONFORM|CONFORM\s+TO))",
            text, re.IGNORECASE,
        )
        if m:
            cand = m.group(1).strip().rstrip(",;:.-").strip()
            if 2 <= len(cand) <= 60 and re.search(r"[A-Za-z0-9]", cand):
                return cand
        m = re.search(
            r"TEI\s+SPECIFICATION\s+([A-Za-z0-9][A-Za-z0-9\-_./]*)"
            r"(?=\s+(?:REV|REVISION|OR\s+LATER|IS\s+APPLICABLE|FOR\s+THIS|$))",
            text, re.IGNORECASE,
        )
        if m:
            cand = m.group(1).strip().rstrip(",;:.-").strip()
            if 2 <= len(cand) <= 60 and re.search(r"[A-Za-z0-9]", cand):
                return cand
        # AMS/PWA/ASTM gibi standart kodlar
        m = re.search(r"\b(AMS\s*\d{4,5}[A-Z]?)\b", text, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", "", m.group(1))
        return ""

    def _material_to_spec(self, material: str) -> str:
        if not material:
            return ""
        m = re.match(r"([A-Z]+\d+)", material.upper())
        return m.group(1) if m else ""
