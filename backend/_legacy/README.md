# Quarantined legacy modules

Moved out of the `app` package during the production-readiness pass. Preserved
(not deleted) for reference; nothing in `app/` imports them.

- `ocr/local_vlm.py` — loaded PaddleOCR-VL **locally in-process** (transformers).
  Violates the remote-only OCR topology and referenced `settings.ocr_local_*`
  attributes that did not exist (would crash). Superseded by
  `app/providers/ocr/paddleocr_vl_provider.py` (remote). Discrepancy #2.
- `ocr/region_router.py` + `ocr/processors/*` — older async OCR design with a
  3-tuple `recognize(client, img, task)` signature that mismatched the live sync
  `OcrEngine`. Never wired. Superseded by the provider pattern.
- `ocr/mock_source.py` — ad-hoc mock; superseded by `app/providers/*/mock_provider.py`.
