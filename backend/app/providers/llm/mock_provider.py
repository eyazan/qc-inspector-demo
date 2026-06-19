"""Mock LLM provider — no remote call.

Returns shape-correct output per call type so the full pipeline completes
offline. The call type is inferred from stable anchors in the system prompt:
  - segmentation  -> valid JSON ({"segments": [...]}) echoing the input regions
  - metadata      -> valid JSON metadata
  - aggregation   -> Turkish markdown narrative
  - comparison    -> Turkish markdown narrative (with result vocabulary)
"""

import json
import re

from app.providers.llm.base import LlmProvider

_REGION_ID_RE = re.compile(r'"region_id"\s*:\s*"([^"]+)"')
_PAGE_RE = re.compile(r'"page_number"\s*:\s*(\d+)')


class MockLlmProvider(LlmProvider):
    name = "mock"
    is_mock = True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if '"segments"' in system_prompt:
            return self._segmentation(user_prompt)
        if "METADATA" in system_prompt.upper() and "JSON" in system_prompt.upper():
            return self._metadata()
        if "KAPSAMLI" in system_prompt:
            return self._aggregation()
        return self._comparison()

    def _segmentation(self, user_prompt: str) -> str:
        region_ids = _REGION_ID_RE.findall(user_prompt)
        pages = [int(p) for p in _PAGE_RE.findall(user_prompt)]
        page_range = [min(pages), max(pages)] if pages else [1, 1]
        segment = {
            "doc_type": "other",
            "page_range": page_range,
            "metadata": {
                "vendor_name": "",
                "material_number": "",
                "heat_lot_number": "",
                "spec_references": [],
            },
            "region_ids": region_ids,
        }
        return json.dumps({"segments": [segment]}, ensure_ascii=False)

    def _metadata(self) -> str:
        return json.dumps(
            {
                "po_number": "4500180435",
                "po_item": "00001",
                "material_number": "AMS4911(20THK)B",
                "spec_references": ["AMS4911", "ASTM B265"],
            },
            ensure_ascii=False,
        )

    def _comparison(self) -> str:
        return json.dumps(
            {
                "findings": [
                    {
                        "parameter": "Kimyasal bilesim (Al)",
                        "result": "COMPLIANT",
                        "severity": "LOW",
                        "spec_section": "3.1",
                        "spec_evidence": "min 5.50 max 6.75 Aluminum",
                        "vendor_page": 1,
                        "vendor_region_ids": ["page1_region0"],
                        "vendor_evidence": "Al 6.10",
                        "rationale": "Vendor Al 6.10 spec araliginda (mock).",
                    },
                    {
                        "parameter": "Mekanik testler",
                        "result": "NOT_COVERED_IN_THIS_DOCUMENT",
                        "severity": "MEDIUM",
                        "spec_section": "3.5",
                        "spec_evidence": "Tensile strength min 130 ksi",
                        "vendor_page": 1,
                        "vendor_region_ids": ["page1_region1"],
                        "vendor_evidence": None,
                        "rationale": "Bu belge turu mekanik testleri kapsamaz (mock).",
                    },
                ]
            },
            ensure_ascii=False,
        )

    def _aggregation(self) -> str:
        return (
            "KAPSAMLI KALITE KONTROL RAPORU - NIHAI DEGERLENDIRME (mock)\n\n"
            "1. YONETICI OZETI\nMock modunda uretildi.\n\n"
            "7. GENEL DEGERLENDIRME VE SONUC\nUYUMLU (mock)\n"
        )
