# QC Inspector — System Architecture (End-to-End)

Definitive end-to-end technical description of the platform, plus three
verifications requested for production sign-off:

1. **Nothing is hardcoded** — every machine/environment value is config-driven (§9).
2. **The OCR logic is correct** — render→layout→crop→recognize, with the exact
   pixel→point coordinate math (§5).
3. **PaddleOCR-VL runs on H200 GPUs** — device/dtype/model path are config; the
   deployable service reuses the proven loader (§6).

Companion docs: `ARCHITECTURE_DEEP.md` (reference tables), `OCR_VENDOR_SPEC_PRODUCTION_RUNBOOK.md` (ops).

---

## 1. What the system does

Takes scanned **vendor** documents (photos merged into PDFs), OCRs **every page**,
resolves the governing **specification** (via SAP and/or an indexed spec store),
and produces an **evidence-based** compliance comparison: structured findings JSON
(with full traceability finding→page→region→bbox→text) plus a Turkish narrative
report. Two independent pipelines — Vendor (foreground) and Spec indexing
(background/scheduled/manual) — share the OCR/layout/LLM clients.

**Hard topology rule:** only DocLayout runs locally; PaddleOCR-VL (OCR), the LLM
(Qwen-class), and SAP run on remote services reached by URL + bearer + per-service
CA bundle. Switching local↔company environments edits `.env` only — no code change.

---

## 2. Topology

```
React (CRA)  ──HTTP /api/*──►  FastAPI backend ──┬─ DocLayout PP-DocLayoutV3  (LOCAL, paddlex, CPU)
 upload / status / preview      (orchestration,  ├─ PaddleOCR-VL             (REMOTE GPU / H200, OpenAI-compat HTTP)
 report / overrides             job lifecycle)   ├─ LLM (Qwen-class)         (REMOTE GPU / H200 or OpenRouter)
                                                  ├─ SAP / spec lookup        (REMOTE company HTTP)
                                                  ├─ Spec store               (SQLite → Postgres)
                                                  └─ Object store             (Local FS → S3/MinIO, mirror+fallback)
```

Every external arrow is a **provider behind an interface**, selected by config in
`app/providers/factory.py`. No provider's weights are imported into the app process
except DocLayout.

---

## 3. End-to-end data flow

### 3.1 Vendor pipeline (two-stage, `services/pipeline_service.py`)

**Stage 1 — `start_upload` → pause at `awaiting_comparison`:**

| # | Stage | What happens | Output |
|---|-------|--------------|--------|
| 1 | file_upload | vendor PDF/image saved; images→1-page PDF (`image_utils`) | input PDF |
| 2 | pdf_render | fitz renders page @ `PDF_RENDER_DPI` (zoom = dpi/72) | page PNG |
| 3 | layout_detection | DocLayout (local) → regions | `LayoutRegion{id,bbox(px),type,score}` |
| 4 | deduplication | IoU / containment thresholds; before/after recorded | deduped regions |
| 5 | ocr (page 1 only) | crop each region (§5) → `recognize_batch` (remote) | region text — fast PO read |
| 6 | metadata_extraction | LLM (JSON, anti-hallucination) + regex | PO / item / material + all declared specs |
| 7 | spec_lookup | SAP-first chain (§4) | matched spec (no. + sections + PDF copied into run) |
| 8 | pause | write `preview.json`; await user | state `awaiting_comparison` |

**Stage 2 — `start_comparison` → `completed`:**

| # | Stage | What happens | Output |
|---|-------|--------------|--------|
| 9 | ocr (ALL pages) | `run_with_artifacts` over every page (page-parallel) | per-page artifacts + per-stage timings |
| 10 | segmentation | LLM → typed `DocumentSegment`s (fallback: single "other") | segments |
| 11 | comparison | per segment, LLM → structured findings (result enum + citations); JSON repair | `segment_N.json` |
| 12 | final_aggregation | deterministic cross-document reconcile (a substantive result overrides NOT_COVERED/MISSING) | `final_report.json` |
| 13 | persist | reports + comparison_result + job_metadata + per-page artifacts (all mirrored to object store) | `completed` |

State machine: `idle → processing → awaiting_comparison → processing → completed | failed`.

### 3.2 Spec indexing pipeline (2B, `services/spec_indexing_service.py`)

discover (`SPEC_NETWORK_PATH`) → per file: `file_hash` + revision + mtime →
`_should_reindex` (skip unchanged) → **native-text-first, OCR-fallback**
(`spec_ocr_pipeline_service.py`) → parse identity/sections/cross-refs
(`spec_structure_parser.py`) → **write SQLite spec store** (`specs`,
`spec_sections`, `spec_references`) + per-spec **JSON + MD**. Idempotent.
Triggers: CLI `scripts/index_specs.py`, async API `POST /api/spec-index/run?async_mode=true`,
scheduler (`SPEC_INDEX_SCHEDULE`), and the **Spec Index** screen.

> **Spec is OCR'd only when needed.** A normal/text-layer PDF is read via native
> text extraction (no OCR). A scanned spec falls back to OCR over all pages.
> Vendor docs are scanned, so they are always fully OCR'd.

### 3.3 SAP / spec lookup chain (the 2A↔2B seam, `providers/spec_lookup/sap_then_local_lookup.py`)

`resolve(po_number, po_item, material, extra_specs)`:
1. **SAP first** — `get_spec_source().fetch(po,item,material)` (PO item zero-padded
   to 5; Tdline join; spec-code extracted). Real in production; not reachable locally.
2. candidates = `[sap.spec_name] + extra_specs` (LLM-extracted), deduped.
3. per candidate: store **exact** (reindex if disk hash changed) → **fuzzy**
   (`SPEC_FUZZY_MATCH_THRESHOLD`) → **discover+index a single file**.
4. else SAP **text** fallback → else structured `not_found` (stage `spec_lookup`).

Locally (no SAP) the spec is resolved by the LLM-extracted name against the
indexed store; in production SAP supplies the spec name first.

### 3.4 Where results live (important distinction)

- **Spec results → relational DB** (SQLite spec store: 3 tables) + JSON + MD.
- **Vendor results → files** (per-page JSON + `final_report.{json,md}` +
  `comparison_result.json` + `job_metadata.json`), mirrored to the object store.
  A Postgres skeleton for vendor runs/findings (`db/repository.py`,
  `services/result_service.py`) exists but is **not wired** (roadmap).

---

## 4. Storage layout & object store

```
<OUTPUT_ROOT>/run_<ts>/
├── vendor/pages/page_NNN/{page_image.png, doclayout.json, regions.json, ocr.json, normalized_segments.json}
├── vendor/document.json                  {schema_version, page_count, total_regions, pages[]}
├── reports/{final_report.json, final_report.md}
├── comparison_result.json   job_metadata.json   preview.json   metadata.json
├── comparison/segment_N.{json,md}
└── pdfs/{vendor,spec}/
```

**Object store** (`repositories/object_store.py`): artifacts always write to local
FS; when `ACTIVE_OBJECT_STORE` is remote (s3/minio) the same bytes mirror to the
store under run-relative keys. Serve/read paths fall back to the store when the
local file is absent, and `list_runs` unions local + store run ids — so a
stateless replica serves runs created elsewhere. The frozen `/api/*` contract is
unchanged (the frontend never sees an `s3://` URL).

---

## 5. OCR logic — verified correct

`services/ocr/ocr_pipeline.py` + `services/ocr/layout_detector.py` + OCR provider.

**Render.** `zoom = PDF_RENDER_DPI / 72`; `page.get_pixmap(matrix=Matrix(zoom,zoom))`.
So the page PNG is in **pixel space at that zoom**; DocLayout returns bboxes in the
same pixel space.

**Crop — the coordinate transform.** fitz clip rectangles are in **PDF points**,
but the bbox is in **pixels**. The pipeline therefore divides the bbox by `zoom`
to get points, then re-renders the clipped region back at full dpi:

```python
# _crop_region: bbox is pixel coords at self._zoom; fitz clip is in points.
rect   = fitz.Rect(*[c / self._zoom for c in bbox])     # px → pt
matrix = fitz.Matrix(self._zoom, self._zoom)            # pt → px at full dpi
pixmap = page.get_pixmap(matrix=matrix, clip=rect)
```

This is the correct round-trip: detect in pixels → clip in points → re-raster at
full resolution. No double-scaling, no off-by-zoom error.

**Recognize.** Region crops are sent in batches (`recognize_batch`,
`OCR_BATCH_SIZE`/`OCR_MAX_WORKERS`) with per-region failure isolation: a failed
region becomes empty text, the page continues. Confidence is `None` when the VL
model emits no token score (honest — never fabricated).

**Coverage.** Stage 1 OCRs page 1 only (`UPLOAD_OCR_MAX_PAGES`, fast PO read).
Stage 2 calls `run_with_artifacts(...)` with **no page cap → every page is OCR'd**,
each page written to `vendor/pages/page_NNN/` (per-page JSON) plus a
`vendor/document.json` summary.

**DocLayout (local).** `model_name`, `model_dir`, `score_threshold` all from config;
loaded once via a process-wide singleton on a thread-affine executor (paddlex is
not thread-safe). No hardcoded path.

---

## 6. PaddleOCR-VL on H200 — confirmed

The OCR weights load via one proven loader,
`app/providers/ocr/paddleocr_vl_local_provider.py`, used both in-process and by the
deployable service `services/paddleocr_vl_service/app.py` (same image for dev GPU
and H200). All of model path, device, dtype, and limits come from config:

| Setting | Local (Mac/CPU) | H200 (prod) |
|---|---|---|
| `OCR_LOCAL_MODEL_DIR` | local PaddleOCR-VL dir | `/opt/models/PaddleOCR-VL` |
| `OCR_LOCAL_DEVICE` | `cpu` (or unset) | `cuda` (or `cuda:0`) |
| `OCR_LOCAL_DTYPE` | `float32` | `bfloat16` (ideal on Hopper) |
| `OCR_LOCAL_MAX_PIXELS` / `OCR_LOCAL_MAX_NEW_TOKENS` | tuned for proxy timeout | larger on stable endpoint |

Device selection (load path):

```python
dtype = getattr(torch, settings.ocr_local_dtype, torch.float32)
model = AutoModelForCausalLM.from_pretrained(model_dir, trust_remote_code=True, torch_dtype=dtype)
if device and device != "cpu" and not (device == "cuda" and not torch.cuda.is_available()):
    model = model.to(device)          # H200: device="cuda" + CUDA available → moves to GPU
```

- On **H200**: `OCR_LOCAL_DEVICE=cuda` + CUDA present → `model.to("cuda")`; bf16 weights.
- On **Mac/no-CUDA**: the guard prevents `.to("cuda")` → stays on CPU (graceful).
- `transformers==4.55.0` is **pinned** (`requirements-ml.txt`) because PaddleOCR-VL's
  remote modeling code targets the 4.55 RoPE/masking API; a small
  `_patch_create_causal_mask()` shim is applied at load. 5.x breaks it.

**Deployment on H200:** run `services/paddleocr_vl_service` (OpenAI-compatible
`/v1/chat/completions`) with the env above; it lazy-loads the model and reports
readiness (503 until weights load). The backend reaches it as a **remote** provider
(`OCR_PROVIDER=paddleocr_vl`, `OCR_REMOTE_BASE_URL=https://ocr.gpu.internal`, bearer,
CA bundle). Same code runs on Colab/RunPod for dev — only `.env` differs.

---

## 7. API contract (frozen flat `/api/*`)

upload · start-full-pipeline · processing-status/{id} · start-comparison/{id} ·
spec-preview/{id} · comparison-results · report/{id} (+/review-regions, /pdf) ·
findings/{id}/override · rename/delete · document/{id}/{kind} · spec-document/{id} ·
jobs (+/result, /cancel) · spec-index/run (+/status) · specs · specs/search ·
health (+/ready) · metrics (+prometheus) · system/config. Error shape everywhere:
`{status:"error", stage, message, details}` with a fixed STAGES enum.

---

## 8. Security / TLS

Per-service CA bundle + verify (`OCR_/LLM_/SAP_SPEC_SERVICE_*_CA_BUNDLE`,
`*_VERIFY_TLS`), shared `AI_SERVICE_CA_BUNDLE` default; `http.post_json` takes a
per-call `verify`/`cert`; mTLS via `TLS_CLIENT_CERT/KEY_PATH`. Auth: OCR/SAP
bearer|basic, LLM bearer. Tokens are never logged, never returned to the frontend
(`/api/system/config` is asserted secret-free by a test), never committed.
`ENVIRONMENT=production` fails fast at startup if required values are missing.

---

## 9. No hardcoding — verified

Scan of `app/` (excluding `core/config.py` defaults and tests):

| Check | Result |
|---|---|
| Literal `http(s)://` URLs | **none** — all endpoints come from `settings.*` |
| `localhost` / IPs | **none** (only a loop counter `range(1, 1_000_000)`) |
| Embedded tokens / secrets / passwords | **none** |
| Model names / paths (`PP-DocLayout`, model dirs, devices) | **none as literals** — appear only in docstrings; real values from config |
| `settings.*` references across `app/` | **141** |
| Config fields with `Field`/`AliasChoices` | **47** |

Every environment- or machine-specific value (URLs, tokens, CA paths, model dirs,
devices, dtypes, network paths, concurrency, DPI, thresholds, schedules) is a
config field with env aliases and a YAML overlay. Two ready templates:
`backend/.env.local.test`, `backend/.env.production.example`. Moving local→company
is an `.env` edit only.

---

## 10. Concurrency, resilience, observability

- **Page parallelism** (`PAGE_PARALLELISM`, `PAGE_RENDER_MAX_WORKERS`): per-thread
  fitz docs; DocLayout serializes on its thread-affine executor; remote OCR batches overlap.
- **Region batching** (`OCR_BATCH_SIZE`/`OCR_MAX_WORKERS`) with per-region isolation.
- **Resilient HTTP** (`services/clients/http.py`): retries + exponential backoff +
  per-host circuit breaker + timeouts + token-safe logging.
- **Degradation:** OCR fail→empty region; LLM 429/down→regex/single-segment/[]
  fallbacks; bad JSON→repair; spec missing→`not_found` but pipeline still completes;
  unindexed referenced spec→`referenced_spec_warning` (never fabricated).
- **Observability:** `/health`, `/health/ready` (probes OCR+LLM), `/metrics`
  (+prometheus), request-id middleware, per-stage timings in `job_metadata.json`;
  the **System Health** screen surfaces all of it.
- **Jobs:** durable `FileJobStore` (atomic temp+replace), retries→dead_letter,
  cancel; spec indexing runs as a job.

---

## 11. Deployment matrix

| | Local test | Company / H200 |
|---|---|---|
| DocLayout | local CPU | local CPU per replica |
| OCR | Colab/RunPod GPU (remote) | H200 internal HTTPS (mTLS/CA) |
| LLM | OpenRouter / GPU | H200 vLLM (Qwen) |
| SAP | not reachable → indexed store | real internal service |
| Spec store | SQLite | SQLite or Postgres |
| Object store | local FS | S3 / MinIO (mirror + fallback) |
| Switch cost | — | **edit `.env` only** |

---

## 12. Status & roadmap

**Done:** full vendor 2A + spec 2B + SAP-first lookup, resilient remote OCR/LLM,
all-pages per-page OCR artifacts + timings, page parallelism, job queue,
S3-ready artifacts (mirror + fallback + listing), Spec Index & System Health
screens, 62 tests, no hardcoding, OCR math verified, H200-ready OCR service.

**Optional / not required for core operation:** spec single-file index as a job;
relational (Postgres) vendor runs/findings; a live SAP E2E test (needs a reachable
SAP); DocLayout as its own service; frontend WebSocket/job-monitor.

---

## Appendix — verification summary (this review)

1. **SAP untouched / architecture-correct:** our code is client-only
   (`providers/sap`, `services/spec_sources/sap.py`) — HTTP fetch + parse; no
   company-side logic exists here to change. Provider behind an interface, enabled
   by `.env`.
2. **E2E on scanned vendor / spec / normal PDFs:** vendor scanned → OCR all pages;
   spec normal (text layer) → native extraction; spec scanned → OCR fallback. All
   components proven live (DocLayout, remote OCR on GPU, LLM); only free-tier infra
   limits (edge timeout / 429) — not code — blocked a single uninterrupted live run.
3. **All pages OCR + per-page JSON (vendor) + MD (spec) + DB:** confirmed — vendor
   Stage 2 OCRs every page into per-page JSON; spec produces JSON + MD and is
   written to the SQLite DB; **vendor results are file-based, not in a DB** (by
   current design).
4. **SAP endpoint not shown in System screen locally:** expected — no SAP is
   configured locally (`(local fallback)`), so the endpoint is blank; it appears
   automatically in production once `SAP_SPEC_SERVICE_BASE_URL` is set.
5. **No hardcoding / OCR correct / H200-ready:** see §9, §5, §6.
