# QC Inspector backend — change summary

Production-readiness pass. Discovery report: [DISCOVERY.md](DISCOVERY.md).
Work landed in 7 verified, committed slices. The frozen `/api/*` frontend
contract was preserved (the brief's `/api/v1/...` names are aspirational; repo wins).

## Added (new modules)

**Config / foundation**
- `.env.example`, `.gitignore`, `requirements.txt`, `requirements-ml.txt`, `README.md`
- `app/core/constants.py` (result enum + TR map + stage list), `app/core/errors.py`
- `app/utils/{bbox_utils,json_utils,hash_utils,image_utils}.py`

**Provider pattern** (`app/providers/`, swap via `ACTIVE_*` config)
- `layout/{base, paddlex_doclayout_provider, mock_provider}`
- `ocr/{base, paddleocr_vl_provider, mock_provider}`
- `llm/{base, openai_compatible_provider, mock_provider}`
- `spec_store/{base, sqlite_spec_store, postgres_spec_store}`
- `spec_lookup/{base, sap_then_local_lookup}`, `factory.py`

**Services / prompts**
- `dedup_service`, `metadata_extraction_service`, `report_renderer`
- `spec_indexing_service`, `spec_file_discovery_service`, `spec_ocr_pipeline_service`,
  `spec_structure_parser`
- `prompts/metadata_extraction.py`

**API / scripts / tests**
- `api/v1/routes_spec_index.py`; registered the orphaned `routes_report` + `routes_override`
- `scripts/{download_models,index_specs,schedule_spec_indexing,test_sap_spec,test_full_pipeline}.py`
- `tests/` (27 passing): PO zero-pad, IoU/dedup, JSON repair, mock OCR/LLM, mock SAP, spec hash

## Changed (key edits, patched not rewritten)
- `core/config.py` — all Section 6 keys + the keys the unfinished DB/compliance
  subsystem referenced but lacked (`database_url`, `db_echo`, `layout_mode`).
- `ocr/ocr_engine.py` — config-driven auth scheme (bearer|basic), discrepancy #1.
- `ocr/ocr_pipeline.py` — fixed pixel→point crop bug; integrated dedup + stats.
- `ocr/layout_detector.py` + `ocr/models.py` — carry layout `score` (was dropped).
- `pipeline_service.py` — LLM metadata + spec lookup strategy + PO seed body +
  structured findings + dual-report persistence.
- `comparison_service` (structured JSON findings) / `aggregation_service`
  (deterministic cross-doc reconciliation) / prompts.
- `storage_service.py` — image→PDF upload, structured report + override + review-regions.
- `routes_pipeline` (seed body), `routes_report`/`routes_override` (file-backed), `main.py` (error handler).

## Retired (quarantined to `backend/_legacy/`, not deleted)
- `ocr/local_vlm.py` (local PaddleOCR-VL load — wrong topology, missing config; discrepancy #2)
- `ocr/region_router.py` + `ocr/processors/*` (broken async OCR design)
- `ocr/mock_source.py`

## What is mock / stub in THIS environment (and how to make real)
- **Layout (PP-DocLayoutV3):** real provider implemented + wired. paddle wheels
  are not yet available for Python 3.14, so the local run used the **mock layout
  provider**. To go real: a Python with paddle support, `pip install -r
  requirements-ml.txt`, `python scripts/download_models.py`,
  `ACTIVE_LAYOUT_PROVIDER=paddlex_doclayout`.
- **OCR (PaddleOCR-VL):** remote-only by design; not reachable here → **mock**.
  Real: set `OCR_SERVICE_URL` + `OCR_BEARER_KEY`, `ACTIVE_OCR_PROVIDER=paddleocr_vl`.
- **LLM (Qwen/vLLM):** remote; not reachable here → **mock**. Real: `LLM_BASE_URL`
  + `LLM_API_KEY`, `ACTIVE_LLM_PROVIDER=openai_compatible`.
- **SAP:** not reachable → `SPEC_SOURCE=local` / mock. Real: SAP endpoint + creds.
- **Postgres spec store:** interface + SQLite live; `postgres_spec_store` is a
  documented stub. Real: implement it, `ACTIVE_SPEC_STORE=postgres`.
- **DB layer (`app/db`, runs/findings/overrides):** the live vendor flow is
  file-based (job-scoped under `data/output/run_<ts>/`); SQLAlchemy layer kept as
  the documented future Postgres path, not auto-initialized.

Everything else (provider wiring, dedup, metadata extraction, spec indexing 2B,
lookup strategy chain, structured + Turkish dual report, all `/api/*` endpoints)
ran for real and is covered by the smoke scripts + unit tests.
