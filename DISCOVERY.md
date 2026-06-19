# QC Inspector — Backend Discovery Report

Status: discovery only, no code changed yet. Ground truth = supplied `backend.zip` (app/-only)
+ `frontend.zip` (src/-only). Where this report and the brief disagree, the **repo wins** (per brief).

## 0. Biggest structural finding (read first)

The **frontend API contract does not match the brief's Section 5 at all.** The brief assumes
`/api/v1/ocr/process-vendor`, `/api/v1/jobs/{id}`, `/api/v1/specs/...`. The real frontend
(`src/services/api.js`) calls a flat `/api/*` surface:

| Frontend call | Method | Served today? |
|---|---|---|
| `/api/query` | POST | YES (routes_spec) |
| `/api/upload` | POST | YES (routes_upload) |
| `/api/start-full-pipeline` | POST | YES (routes_pipeline) — **ignores PO body** |
| `/api/processing-status/{run_id}` | GET | YES |
| `/api/cancel-processing/{run_id}` | POST | YES |
| `/api/comparison-results` | GET | YES (routes_results) |
| `/api/comparison-results/{id}` | DELETE | YES |
| `/api/comparison-results/{id}/rename` | POST | YES |
| `/api/report/{id}` | GET | YES |
| `/api/report/{id}/review-regions` | GET | **MISSING — no route anywhere** |
| `/api/report/{id}/pdf` | GET | **BROKEN — route file exists but not registered** |
| `/api/findings/{id}/override` | POST | **BROKEN — route file exists but not registered** |
| `/health` | GET | YES |

Decision implied by the brief's own rule: **keep the `/api/*` contract, do not migrate to
`/api/v1/...`.** The brief's Section 5/7 names are treated as aspirational, not a target to force.

## 1. Module classification

### Wired & working (the live runtime)
- `main.py`, `core/config.py`, `core/logging.py` — clean, all config via pydantic-settings/env.
- `api/v1/router.py` registers: health, spec, upload, pipeline, results.
- `services/pipeline_service.py` — **two-stage** flow (Stage 1 upload→preview→PAUSE,
  Stage 2 comparison). More nuanced than brief's single 2A pipeline.
- `services/storage_service.py` — file-based, job-scoped under `data/output/run_<ts>/` (already
  job-scoped, resolves discrepancy #5 in our favor).
- `services/ocr/ocr_pipeline.py` — render→layout→crop→OCR, sync, bounded by `ocr_max_concurrency`.
- `services/ocr/layout_detector.py` — **local PP-DocLayoutV3 via paddlex** (correct per topology).
- `services/ocr/ocr_engine.py` — **remote** PaddleOCR-VL, OpenAI-compatible, **Bearer** auth.
- `services/clients/{http,llm_client}.py` — shared httpx client w/ TLS + mTLS cert wiring.
- `services/segmentation_service.py` — LLM segmentation, **has JSON-repair fallback**.
- `services/comparison_service.py`, `aggregation_service.py` — LLM, output **Turkish markdown**.
- `services/spec_sources/{sap,local}.py` — SAP uses **Basic** auth; selectable via `spec_source`.
- `services/spec_finder.py`, `services/spec_index_service.py` — **file-based** spec index (JSON+MD).
- `services/vendor_po_parser.py` — **regex** PO/item/material extraction (not LLM).
- `services/pipeline_state.py` — in-memory run state.

### Stub / partial
- `start_full_pipeline` route ignores `po_number/po_item/material/inspector_id` from the body;
  PO data comes only from OCR of the uploaded file. Frontend sends them → silently dropped.
- `prompts/*` encode anti-hallucination rules and Turkish vocab (UYUMLU/UYUMSUZ/BU BELGEDE
  KAPSANMIYOR) **but emit free-form markdown** — no structured `finding_id`/`result` enum/citation
  JSON (brief Section 4/8 not implemented). comparison/aggregation lack JSON-repair (segmentation has it).
- `vendor_po_parser` captures one material; brief 0.5 wants **all declared specs per segment**.

### Dead / unwired (parallel, never imported into the live path)
- **DB layer**: `core/database.py`, `db/models.py` (Run/Document/Region/Segment/Finding/Override/
  SpecRequirement/SpecIndex — a richer design), `db/repository.py`. `init_db()` is **never called**;
  only the orphaned override route + result_service touch it → would fail at runtime.
- `api/v1/routes_report.py`, `routes_override.py` — **not registered** in router.py.
- `services/result_service.py`, `services/report_service.py` — used only by orphaned routes.
- `services/compliance_service.py` + `services/unit_converter.py` — 0 live refs.
- `services/ocr/region_router.py` + `processors/{base,text,table,figure,formula}.py` — 0 refs;
  async 3-tuple `recognize(client, img, task)` signature mismatches the live sync `OcrEngine`.
- `services/ocr/local_vlm.py` — **loads PaddleOCR-VL locally** (violates remote-only topology) and
  references `settings.ocr_local_*` attrs that **don't exist in config** → would crash. Leftover
  experiment (discrepancy #2). 0 refs — safe to retire/quarantine.
- `services/ocr/mock_source.py` — 0 refs.
- `services/spec_parser.py` — 0 refs (brief wants section/clause + cross-ref parsing; not wired).
- `workers/spec_sync_worker.py` — 0 refs (this is the intended 2B background indexer; not wired).

### Missing entirely (not in the zip — `app/`-only)
- `requirements.txt` / `pyproject.toml`, `.env.example`, `.env`, `.gitignore`
- `scripts/` (download_models, test_sap_spec, test_full_pipeline, index_specs, schedule)
- `models/` (PP-DocLayoutV3 weights), `data/` tree, `tests/`, `README.md`
- `prompts/metadata_extraction.py` (brief Section 4 wants it; today extraction is regex)
- `providers/` pattern (brief Section 6) — does not exist; closest analog is `spec_sources/`.
- `/api/report/{id}/review-regions` endpoint (frontend needs it).
- Structured JSON `final_report` + `final_report_text` dual output (brief 0.7 #6).
- IoU dedup service (brief 2A step 7) — no dedup anywhere.

## 2. Section 0.7 discrepancy resolutions
1. **OCR auth** → **Bearer** (`ocr_engine.py`, `OCR_BEARER_KEY`). SAP is Basic. Resolved.
2. **PaddleOCR-VL local model** → `local_vlm.py` is dead + broken (missing config attrs). Remote-only
   confirmed via `ocr_engine.py`. No `models/PaddleOCR-VL-*` dir present in zip. Quarantine, don't load.
3. **Two OCR entry points** → no `process-image` base64 endpoint exists; only the upload→pipeline
   flow. The `processors/` tree is the dead older async design. Frontend uses upload+start-pipeline.
4. **Test script names** → none exist in zip; will create per brief Section 8, no conflict.
5. **Output layout** → already job-scoped (`data/output/run_<ts>/...`). No migration needed.
6. **Report shape** → only Turkish markdown narrative exists; structured JSON findings do NOT.
   Both are required; structured layer must be added without duplicating compare/segment logic.

## 3. Secrets / hygiene
- No hardcoded URLs/IPs/tokens in code — all via `config.py` (good).
- `app/certificates/` ships CA/intermediate certs (`TeidomCAROOT.crt`, `ESET_SSL_Filter_CA.crt`,
  `certar.cer`, `paddle_ca_bundle.crt`). These are CA certs, not private keys — but committing them
  is worth flagging; path should be config-driven, no client `.key` present (good).
- No `.gitignore` → risk of committing `.env`/`data/`. Must add.
