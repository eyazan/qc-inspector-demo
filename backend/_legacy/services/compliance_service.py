"""
Compliance Service — iki katmanli compliance motoru.

Katman 1 (deterministik): vendor segmentinden sayisal degerleri yakala,
  requirement'larla unit-aware + tolerance karsilastir. Kesin matematik.
Katman 2 (LLM): deterministik katmanin cozemedigi (metinsel, baglamsal)
  gereksinimler + her bulgu icin denetciye yonelik gerekce uret.

Cikti: yapisal finding listesi (DB'ye yazilir, UI'da gosterilir, override'lanir).
"""

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.segment_comparison import (
    SEGMENT_SYSTEM_PROMPT,
    build_comparison_user_prompt,
)
from app.services.clients.llm_client import LlmClient
from app.services.ocr.models import DocumentSegment
from app.services.unit_converter import can_compare, convert_for_comparison

logger = get_logger(__name__)

# Vendor metninde "deger + birim" yakalama: "410 MPa", "320 HB", "0.18 %"
_VALUE_UNIT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(MPa|N/mm2|N/mm²|ksi|psi|GPa|kPa|bar|HB|HV|HRC|HRB|%|mm|cm|°C|°F)",
    re.IGNORECASE,
)


class ComplianceService:
    def __init__(self):
        self._llm = LlmClient(settings.comparison_timeout_seconds)
        self._tolerance = settings.borderline_threshold_ratio

    def evaluate(
        self,
        segment: DocumentSegment,
        requirements: list[dict],
    ) -> tuple[list[dict], str]:
        """
        Returns: (findings, markdown_report)
        findings -> DB'ye; markdown_report -> nihai aggregation icin.
        """
        # --- Katman 1: deterministik ---
        vendor_values = self._extract_vendor_values(segment)
        deterministic_findings, matched_params = self._deterministic_check(
            requirements, vendor_values
        )

        # --- Katman 2: LLM (deterministik cozemedikleri + gerekce) ---
        # Mock modda LLM yok; deterministik bulgulardan ozet rapor uret.
        if settings.layout_mode == "mock":
            llm_report = self._mock_report(segment, deterministic_findings)
        else:
            llm_report = self._llm_compare(segment, requirements)

        return deterministic_findings, llm_report

    def _mock_report(self, segment: DocumentSegment, findings: list[dict]) -> str:
        """LLM olmadan, deterministik bulgulardan markdown ozet (mock modu)."""
        lines = [f"## {segment.doc_type} — Uygunluk Ozeti (mock)\n"]
        if not findings:
            lines.append("Deterministik eslesme bulunamadi.")
        for f in findings:
            lines.append(
                f"- **{f['parameter']}**: {f['status']} "
                f"(spec {f.get('spec_value')}, vendor {f.get('vendor_value')}) — {f.get('rationale','')}"
            )
        return "\n".join(lines)

    def _extract_vendor_values(self, segment: DocumentSegment) -> list[dict]:
        """Segment icindeki tum 'deger + birim' ciftlerini topla (tablo + metin)."""
        values = []
        for region in segment.content:
            # Once yapisal tablo verisi (en guvenilir)
            structured = region.get("structured_data")
            if structured and structured.get("format") == "table":
                values.extend(self._values_from_table(structured, region))
            # Sonra ham metin
            text = region.get("text", "")
            for match in _VALUE_UNIT_PATTERN.finditer(text):
                # Context: degerin SOLUNDAki en yakin etiket (deger genelde
                # "Parametre: deger" formatinda, etiket solda olur).
                left = text[max(0, match.start() - 50) : match.start()]
                values.append(
                    {
                        "value": _parse_num(match.group(1)),
                        "unit": match.group(2),
                        "context": left,
                        "page": region.get("page_number"),
                    }
                )
        return values

    def _values_from_table(self, structured: dict, region: dict) -> list[dict]:
        values = []
        rows = structured.get("rows", [])
        for row in rows:
            row_text = " ".join(str(c) for c in row)
            for match in _VALUE_UNIT_PATTERN.finditer(row_text):
                values.append(
                    {
                        "value": _parse_num(match.group(1)),
                        "unit": match.group(2),
                        "context": row_text,
                        "page": region.get("page_number"),
                    }
                )
        return values

    def _deterministic_check(
        self, requirements: list[dict], vendor_values: list[dict]
    ) -> tuple[list[dict], set]:
        findings = []
        matched = set()

        for req in requirements:
            best = self._find_best_match(req, vendor_values)
            if best is None:
                continue  # deterministik eslesme yok -> LLM katmanina birak

            matched.add(req["parameter"])
            status, deviation, severity, rationale = self._judge(req, best)
            findings.append(
                {
                    "requirement_id": req.get("id"),
                    "parameter": req["parameter"],
                    "spec_value": self._spec_value_str(req),
                    "vendor_value": f"{best['value']} {best['unit']}",
                    "unit": req.get("unit"),
                    "status": status,
                    "severity": severity,
                    "rationale": rationale,
                    "spec_section": req.get("section_ref"),
                    "page_ref": best.get("page"),
                    "deviation_pct": deviation,
                    "source": "deterministic",
                }
            )
        return findings, matched

    def _find_best_match(self, req: dict, vendor_values: list[dict]) -> dict | None:
        """
        Requirement ile eslesen vendor degerini bul.

        Onemli: yanlis eslesmeyi onlemek icin parametre adi vendor context'inde
        GECMELI. Sadece birim uyumu yetmez (orn. ayni birimde 3 farkli deger varsa
        hangisinin hangi parametre oldugu context'ten anlasilir). Context'te
        parametre adi yoksa deterministik eslesme YAPMA -> LLM katmanina birak.
        Bu, 'hicbir seyi kacirma' + 'yanlis pozitif uretme' dengesini korur.
        """
        req_unit = req.get("unit")
        candidates = [
            v for v in vendor_values if can_compare(req_unit, v["unit"])
        ]
        if not candidates:
            return None

        # Parametre adindaki anlamli kelimeler context'te geciyor mu?
        param_words = [w for w in self._param_keywords(req["parameter"]) if len(w) > 2]
        for v in candidates:
            ctx = v["context"].lower()
            if param_words and any(word in ctx for word in param_words):
                return v

        # Parametre adi hicbir context'te yoksa: tek aday varsa ve birim
        # ailesi nadirse (orn. sadece bir HB degeri) guvenle esle; aksi halde
        # belirsizligi LLM'e birak.
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _param_keywords(self, parameter: str) -> list[str]:
        """Parametre adini ayirt edici TR/EN anahtar kelimelere ayir."""
        synonyms = {
            "tensile": ["tensile", "cekme"],
            "yield": ["yield", "akma"],
            "hardness": ["hardness", "sertlik", "hb", "hv", "hrc"],
            "carbon": ["carbon", "karbon"],
            "elongation": ["elongation", "uzama"],
            "impact": ["impact", "darbe", "charpy"],
            "manganese": ["manganese", "mangan", "mn"],
            "silicon": ["silicon", "silisyum", "si"],
            "sulfur": ["sulfur", "sulphur", "kukurt"],
            "phosphorus": ["phosphorus", "fosfor"],
        }
        # Generic kelimeler ayirt edici degil -> elenir
        stopwords = {
            "strength", "dayanim", "dayanimi", "value", "deger", "test",
            "min", "max", "minimum", "maximum", "nominal", "the", "of", "and",
        }
        words = [w for w in parameter.lower().split() if w not in stopwords]
        expanded = list(words)
        for word in words:
            for key, syns in synonyms.items():
                if word == key or word in syns:
                    expanded.extend(syns)
        return list(set(expanded))

    def _judge(self, req: dict, vendor: dict) -> tuple[str, float | None, str, str]:
        """Deterministik karar: COMPLIANT / NON_COMPLIANT / PARTIAL."""
        req_unit = req.get("unit")
        v_converted = convert_for_comparison(vendor["value"], vendor["unit"], req_unit)
        if v_converted is None:
            v_converted = vendor["value"]

        limit_type = req.get("limit_type", "exact")
        vmin, vmax, vexact = req.get("value_min"), req.get("value_max"), req.get("value_exact")

        def deviation_from(limit):
            if limit in (None, 0):
                return None
            return round((v_converted - limit) / abs(limit) * 100, 2)

        # min: vendor >= min olmali
        if limit_type == "min" and vmin is not None:
            dev = deviation_from(vmin)
            if v_converted >= vmin:
                status = "COMPLIANT"
                if v_converted <= vmin * (1 + self._tolerance):
                    status = "PARTIAL"  # sinirda
                return status, dev, _sev(status), f"Vendor {v_converted:.2f} >= spec min {vmin}"
            return "NON_COMPLIANT", dev, "HIGH", f"Vendor {v_converted:.2f} < spec min {vmin}"

        # max: vendor <= max olmali
        if limit_type == "max" and vmax is not None:
            dev = deviation_from(vmax)
            if v_converted <= vmax:
                status = "COMPLIANT"
                if v_converted >= vmax * (1 - self._tolerance):
                    status = "PARTIAL"
                return status, dev, _sev(status), f"Vendor {v_converted:.2f} <= spec max {vmax}"
            return "NON_COMPLIANT", dev, "HIGH", f"Vendor {v_converted:.2f} > spec max {vmax}"

        # range: vmin <= vendor <= vmax
        if limit_type == "range" and vmin is not None and vmax is not None:
            if vmin <= v_converted <= vmax:
                return "COMPLIANT", None, "LOW", f"Vendor {v_converted:.2f} araliginda [{vmin}, {vmax}]"
            target = vmin if v_converted < vmin else vmax
            return "NON_COMPLIANT", deviation_from(target), "HIGH", (
                f"Vendor {v_converted:.2f} aralik disinda [{vmin}, {vmax}]"
            )

        # exact/nominal
        if vexact is not None:
            dev = deviation_from(vexact)
            if abs(v_converted - vexact) <= abs(vexact) * self._tolerance:
                return "COMPLIANT", dev, "LOW", f"Vendor {v_converted:.2f} ~ spec {vexact}"
            return "NON_COMPLIANT", dev, "MEDIUM", f"Vendor {v_converted:.2f} != spec {vexact}"

        return "PARTIAL", None, "MEDIUM", "Deterministik karar verilemedi, LLM degerlendirmesi gerekli"

    def _spec_value_str(self, req: dict) -> str:
        lt = req.get("limit_type")
        unit = req.get("unit") or ""
        if lt == "min":
            return f"min {req.get('value_min')} {unit}".strip()
        if lt == "max":
            return f"max {req.get('value_max')} {unit}".strip()
        if lt == "range":
            return f"{req.get('value_min')}-{req.get('value_max')} {unit}".strip()
        if req.get("value_exact") is not None:
            return f"{req.get('value_exact')} {unit}".strip()
        return req.get("raw_text", "") or ""

    def _llm_compare(self, segment: DocumentSegment, requirements: list[dict]) -> str:
        """LLM ile metinsel/baglamsal karsilastirma + gerekce (markdown rapor)."""
        # Spec'in TAMAMI yerine kompakt requirement listesini gonder (token tasarrufu)
        spec_compact = self._requirements_to_text(requirements)
        user_prompt = build_comparison_user_prompt(segment.to_dict(), spec_compact)
        try:
            return self._llm.complete(SEGMENT_SYSTEM_PROMPT, user_prompt)
        except Exception as error:  # noqa: BLE001
            logger.error("LLM karsilastirma hatasi: %s", error)
            return f"LLM karsilastirma basarisiz: {error}"

    def _requirements_to_text(self, requirements: list[dict]) -> str:
        lines = ["# SARTNAME GEREKSINIMLERI (yapisal liste)\n"]
        for req in requirements:
            section = req.get("section_ref") or "-"
            lines.append(
                f"- [{section}] {req['parameter']}: {self._spec_value_str(req)} "
                f"({req.get('category', 'other')})"
            )
        return "\n".join(lines)


def _parse_num(text: str) -> float:
    return float(text.replace(",", "."))


def _sev(status: str) -> str:
    return {"COMPLIANT": "LOW", "PARTIAL": "MEDIUM", "NON_COMPLIANT": "HIGH"}.get(status, "MEDIUM")
