# QC Inspector — Deep Technical Architecture

Exhaustive reference for the backend + frontend: every component, contract,
schema, config key, failure mode, and seam. Pairs with
`OCR_VENDOR_SPEC_PRODUCTION_RUNBOOK.md` (ops) and `ARCHITECTURE.md` (overview).

---

## 0. Topology & invariants

- **Local machine:** API + **DocLayout only** (PP-DocLayoutV3, paddlex, CPU).
- **Remote GPU (H200 / dev Colab/RunPod):** PaddleOCR-VL (OCR), Qwen-class LLM —
  both OpenAI-compatible HTTP, reached by URL + bearer + per-service CA bundle.
- **Remote internal:** SAP/spec lookup service.
- **Invariant:** all machine-specific values live in `.env`/`app/core/config.py`
  only. No model is imported by the app process except DocLayout. Providers are
  swapped by config; no mocks or hardcoded data in the active path.

```
                    ┌──────────────────────────── FastAPI backend ────────────────────────────┐
 React (/api/*) ───▶│ routes_* ─▶ PipelineService (2A) ─┬─ get_layout_provider ─▶ DocLayout(local)│
                    │            SpecIndexingService(2B) ├─ get_ocr_provider ────▶ PaddleOCR-VL(remote)
                    │            JobQueue (async)         ├─ get_llm_provider ────▶ Qwen LLM(remote)
                    │                                     ├─ get_spec_lookup ─────▶ SAP + SpecStore
                    │                                     └─ get_object_store ────▶ FS / S3            │
                    └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Component inventory (path → responsibility)

**core/**
- `config.py` — pydantic-settings; every setting + AliasChoices + per-service TLS
  resolvers + `validate_for_providers()` fail-fast + YAML overlay.
- `logging.py` — structured logging (no secrets). `errors.py` — `PipelineStageError`
  + `{status,stage,message,details}` shape + STAGES enum. `constants.py` — result
  enum (`COMPLIANT|NON_COMPLIANT|NOT_COVERED_IN_THIS_DOCUMENT|MISSING|UNCLEAR`),
  TR labels, `to_frontend_status`. `metrics.py` — in-process counters/latency.
  `database.py` — SQLAlchemy engine (future Postgres for runs/findings; unwired).

**providers/** (interfaces + impls + `factory.py`)
- `layout/` base + `paddlex_doclayout_provider` (wraps thread-affine LayoutDetector).
- `ocr/` base (+`recognize_batch`) + `paddleocr_vl_provider` (remote) +
  `paddleocr_vl_local_provider` (in-process transformers, single loader).
- `llm/` base + `openai_compatible_provider` (vLLM/Qwen/OpenRouter/Gemini).
- `spec_store/` base + `sqlite_spec_store` (+`postgres_spec_store` stub).
- `spec_lookup/` base + `sap_then_local_lookup` (the 2A↔2B seam).
- `sap/` `RealSAPProvider` + real local-file fallback (no fabricated data).

**services/**
- `pipeline_service` — vendor 2A two-stage orchestration.
- `ocr/ocr_pipeline` — render→layout→dedup→crop→OCR; `run()` + `run_with_artifacts()`.
- `ocr/layout_detector` — paddlex load (singleton) + thread-affine executor.
- `dedup_service` — IoU + containment dedup. `metadata_extraction_service` — LLM
  + regex PO/item/material/all-specs. `segmentation_service`, `comparison_service`
  (structured findings), `aggregation_service` (deterministic reconcile),
  `report_renderer` (TR narrative). `spec_indexing_service`,
  `spec_file_discovery_service`, `spec_ocr_pipeline_service`, `spec_structure_parser`,
  `spec_finder`. `storage_service` (file artifacts), `scheduler` (APScheduler),
  `pipeline_state` (in-memory run state), `clients/{http,llm_client}`.

**jobs/** `models`(Job+FileJobStore atomic) `queue`(InProcess+Celery stub) `factory`.
**repositories/** `object_store` (LocalFs + S3). **prompts/** 4 prompt files.
**api/v1/** routes_{health,spec,upload,pipeline,results,report,override,spec_index,jobs}.
**services/paddleocr_vl_service/** deployable OCR HTTP server. **scripts/**, **tests/** (56).

---

## 2. Provider selection matrix

| Capability | Config key | Values | Default |
|---|---|---|---|
| Layout | `DOCLAYOUT_PROVIDER`/`ACTIVE_LAYOUT_PROVIDER` | `paddlex_doclayout` | local |
| OCR | `OCR_PROVIDER`/`ACTIVE_OCR_PROVIDER` | `paddleocr_vl` (remote), `paddleocr_vl_local` | remote |
| LLM | `LLM_PROVIDER`/`ACTIVE_LLM_PROVIDER` | `openai_compatible` | remote |
| Spec store | `ACTIVE_SPEC_STORE` | `sqlite`, `postgres` | sqlite |
| Spec lookup | `ACTIVE_SPEC_LOOKUP_STRATEGY` | `sap_then_local_store` | — |
| SAP | `ACTIVE_SAP_PROVIDER` | `real`, `local` | derived from endpoint |
| Object store | `ACTIVE_OBJECT_STORE` | `local`, `s3` | local |
| Job queue | `ACTIVE_JOB_QUEUE` | `inprocess`, `celery` | inprocess |

All interfaces are ABCs; `factory.py` is the only place that maps config→impl.

---

## 3. Vendor pipeline (2A) — stage by stage

`PipelineService.start_upload(seed)` → thread → `_run_upload` (Stage 1):
1. **file_upload** — vendor PDF/image in `data/input/vendor` (images→1-page PDF).
2. **pdf_render** — fitz at `PDF_RENDER_DPI`.
3. **layout_detection** — DocLayout per page → `LayoutRegion{region_id,bbox(px),type,score}`.
4. **deduplication** — IoU>`DEDUP_IOU_THRESHOLD` / containment>`DEDUP_CONTAINMENT_THRESHOLD`; before/after recorded.
5. **ocr** — crop (px→pt fix) → `recognize_batch` (remote, `OCR_BATCH_SIZE`).
   Stage 1 OCRs first page only (`UPLOAD_OCR_MAX_PAGES`) for fast PO read.
6. **metadata_extraction** — LLM (JSON, anti-hallucination) + regex fallback →
   PO/item/material + ALL declared specs.
7. **spec_lookup** — strategy chain (§5). Copies matched spec PDF into the run.
8. **pause** → `awaiting_comparison`; `preview.json` written.

`start_comparison` → `_run_comparison` (Stage 2):
9. **ocr (full)** — `run_with_artifacts` over ALL pages (page-parallel) → per-page
   artifacts + timings.
10. **segmentation** — LLM → typed `DocumentSegment`s (DOCUMENT_TYPES enum); fallback
    to a single "other" segment on malformed output.
11. **comparison** — per segment, LLM → structured findings (result enum + citations);
    JSON repair.
12. **final_aggregation** — deterministic cross-document reconcile (a substantive
    result overrides NOT_COVERED/MISSING from another segment); `finding_id`,
    summary counts, `referenced_spec_warnings`.
13. **persist** — `final_report.json` + `final_report.md` + `comparison_result.json`
    + `job_metadata.json` (timings) + per-page artifacts. `completed`.

State machine (`pipeline_state`): `idle→processing→awaiting_comparison→processing→completed|failed`.

---

## 4. Spec indexing (2B)

`SpecIndexingService.run(mode, spec_name)`:
discover (`SpecFileDiscoveryService` over `SPEC_NETWORK_PATH`) → per file:
`file_hash` (`SPEC_HASH_ALGORITHM`) + revision + mtime → `_should_reindex`
(`SPEC_REINDEX_IF_HASH_CHANGED`/`_REVISION_CHANGED`) → native-text
(`SpecOcrPipelineService`) else OCR fallback → `spec_structure_parser`
(identity, sections, cross-refs) → `SqliteSpecStore.upsert_spec/replace_sections/
replace_references` → per-spec JSON+MD in `SPEC_OUTPUT_DIR`. Idempotent.
Modes: `full` (force), `incremental` (skip unchanged), `--spec-name` (filter).
Entry points: CLI `scripts/index_specs.py`, async API
`POST /api/spec-index/run?async_mode=true`, scheduler (`SPEC_INDEX_SCHEDULE`).

---

## 5. SAP / spec lookup chain (the 2A↔2B seam)

`SapThenLocalLookup.resolve(po_number, po_item, material, extra_specs)`:
1. `get_spec_source().fetch(po,item,material)` — **SAP first** (real provider when
   endpoint configured; PO item zero-padded to 5; Tdline join; spec-code extracted).
2. candidates = `[sap.spec_name] + extra_specs` (LLM-extracted), deduped.
3. per candidate: store **exact** (reindex if disk hash changed) → **fuzzy**
   (`SPEC_FUZZY_MATCH_THRESHOLD`) → **discover+index a single file** on the root.
4. else SAP **text** fallback (usable for comparison).
5. else `SpecLookupResult{status:not_found, stage:spec_lookup|sap_spec_fetch}`.
Returns `{status,source,spec_no,spec_text,sections,references,file_path,stage,message}`.
Local (no SAP): resolves via extracted spec name + indexed store (verified).

---

## 6. API contract (frozen `/api/*`)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/upload` | multipart file, is_spec | `{status,filename,is_spec,saved_path}` |
| POST | `/api/start-full-pipeline` | `{po_number,po_item,material,inspector_id}` | `{status,run_id,message}` |
| GET | `/api/processing-status/{run_id}` | — | `{is_processing,current_step,progress,logs,status,start/end_time,...}` |
| POST | `/api/start-comparison/{run_id}` | — | `{status,run_id,message}` |
| GET | `/api/spec-preview/{run_id}` | — | preview (po/material/sap_spec_text/spec_doc_status/...) |
| GET | `/api/comparison-results` | — | `[{id,type,vendor_file,spec_file,po_info,display_name,timestamp,...}]` |
| GET | `/api/report/{id}` | — | `{id,po_number,po_item,material,summary,findings[],...}` |
| GET | `/api/report/{id}/review-regions` | — | `[ReviewRegion]` (array) |
| GET | `/api/report/{id}/pdf` | — | application/pdf |
| POST | `/api/findings/{id}/override` | `{action,new_status,new_value,note,inspector_id}` | `{status,finding_id,new_status}` |
| POST/DELETE | `/api/comparison-results/{id}/rename` · `/{id}` | — | `{status,message}` |
| GET | `/api/document/{run_id}/{kind}` · `/api/spec-document/{run_id}` | — | pdf |
| GET/POST | `/api/v1/jobs` · `/{id}` · `/{id}/result` · `/{id}/cancel` | — | Job |
| POST/GET | `/api/spec-index/run` · `/status/{id}` · `/api/specs/search` · `/{id}` | — | — |
| GET | `/health` · `/api/v1/health` · `/health/ready` · `/metrics` · `/metrics/prometheus` | — | — |
Errors everywhere: `{status:"error",stage,message,details}` with STAGES enum.

---

## 7. Storage layout & JSON schemas

```
<OUTPUT_ROOT>/run_<ts>/
├── vendor/pages/page_NNN/{page_image.png, doclayout.json, regions.json, ocr.json, normalized_segments.json}
├── vendor/document.json            {schema_version, page_count, total_regions, pages[]}
├── reports/{final_report.json, final_report.md}
├── comparison_result.json          # = final_report
├── job_metadata.json               {run_id, po/item/material, spec_no, page_count, region_count, dedup_stats, timings}
├── preview.json, metadata.json, comparison/segment_N.{json,md}, pdfs/{vendor,spec}/
```
- `ocr.json.regions[]` = `{region_id,text,bbox,page_number,region_type,confidence}`.
- **finding** = `{finding_id,parameter,result,severity,spec_section,spec_evidence,
  vendor_page,vendor_region_ids[],vendor_evidence,rationale,evidence_segments[]}`.
- **final_report** = `{run_id,summary{enum:count},total_findings,findings[],
  referenced_spec_warnings[],reconciliation_notes[],dedup_stats}`.
- SQLite spec store: `specs(spec_no,spec_no_norm,revision,file_path,content_hash,
  modified_time,status,output_*_path,text,indexed_at)`, `spec_sections(section_no,
  title,page_number,text)`, `spec_references(referenced_spec_no,context,page_number,indexed)`.
- Job record: `{id,type,status,params,result,error,attempts,max_attempts,created/updated_at}`.

---

## 8. Security / TLS model

- Per-service CA bundle + verify: `OCR_/LLM_/SAP_SPEC_SERVICE_*_CA_BUNDLE` +
  `*_VERIFY_TLS`; shared `AI_SERVICE_CA_BUNDLE` default. `http.post_json` takes
  per-call `verify`(CA path|bool)/`cert`. mTLS via `TLS_CLIENT_CERT/KEY_PATH`.
- Auth: OCR bearer|basic (`OCR_AUTH_SCHEME`); LLM bearer; SAP bearer|basic.
- Secrets never logged (token-safe logging), never in frontend responses, never
  committed (`.env` gitignored). Fail-fast in `ENVIRONMENT=production`.

---

## 9. Concurrency / performance model

- **Page parallelism** (`PAGE_PARALLELISM`, `PAGE_RENDER_MAX_WORKERS`): per-thread
  fitz docs; DocLayout serializes on its thread-affine executor; remote OCR batches
  overlap across pages.
- **Region batching** (`OCR_BATCH_SIZE`/`OCR_MAX_WORKERS`): a page's crops sent
  concurrently; per-region failure isolation.
- **Resilience**: retries+backoff, per-host circuit breaker, timeouts.
- **Timings** per stage (render/doclayout/ocr/segmentation/comparison) logged +
  in `job_metadata.json`.

---

## 10. Failure modes & graceful degradation

| Failure | Behavior |
|---|---|
| OCR region 5xx/timeout (after retries) | that region → empty text; page continues |
| OCR circuit open | fast-fail; isolated per host |
| LLM 429/down | metadata→regex fallback; segmentation→single segment; comparison→[] |
| Malformed LLM JSON | `json_utils` repair → default |
| Spec not found | structured `not_found` (stage spec_lookup); pipeline still completes |
| Referenced spec not indexed | `referenced_spec_warning` (never fabricated) |
| Bad/empty/oversized PDF | validation error surfaced to frontend (stage file_upload/pdf_render) |
| Config missing (prod) | startup fails fast with the missing keys listed |

---

## 11. Observability & jobs

- `/health` liveness, `/health/ready` (probes OCR+LLM), `/metrics`(+prometheus).
- Request-id middleware; per-request method/path/status/latency logs.
- Jobs: durable `FileJobStore` (atomic writes), retries→dead_letter, cancel;
  Submit/Status/Result/Cancel APIs; spec indexing runs as a job.

---

## 12. Test inventory (60)

PO zero-pad · IoU/dedup · JSON repair · resilient client (retry/exhaust/breaker) ·
OCR engine wire-contract + batch isolation + auth · OCR service contract ·
provider/config switching + aliases · job submit/dead-letter/cancel · object store ·
artifact mirror + serve/read fallback from store · SAP provider selection + parsing
(stubbed transport) · report contract + status mapping + override · per-page
artifacts (both pages, all files) · metrics/health + system-config non-secret +
specs-list shape · spec hash/revision change.

---

## 13. Known gaps / assumptions / roadmap

- **No live SAP call tested** (no SAP available); client unit-tested with stubbed
  transport — set `SAP_SPEC_SERVICE_BASE_URL` to exercise live.
- **Runs/findings file-based** (relational `RunRepository`/Postgres = next).
- **Job queue in-process** (Celery/Redis = drop-in via `ACTIVE_JOB_QUEUE`).
- **Object store**: run artifacts write to local FS and, when `ACTIVE_OBJECT_STORE`
  is remote (s3/minio), mirror to the store under run-relative keys; PDF/report
  serve + read paths fall back to the store when the local file is absent (a
  stateless replica can serve another replica's run) — no `/api/*` contract change.
  Remaining for *pure* S3 (no local disk): the glob-based cross-run listing
  (`list_runs`/`list_comparison_results`) still scans local FS, so multi-run
  history needs a shared volume or an `ObjectStore.list(prefix)` migration.
- **Single-file spec index is synchronous** inside lookup (could be a job).
- **OCR proxy timeout** on huge regions (cap tokens / H200 endpoint).
- **Frontend**: polling (no WS). Spec-index + system-health/config screens added
  (`/spec-index`, `/system-health`); a live job-monitor view is still open.
- **DocLayout single-thread** (CPU); a DocLayout service would lift the local bound.
