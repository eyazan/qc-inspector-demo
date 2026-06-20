# QC Inspector — Production Architecture & Refactoring Plan

Scope: refactor the existing QC Inspector toward a production-grade, fully
configurable, scalable OCR + document-comparison platform **without** rewriting
the business flow. This document grounds every recommendation in the code that
already exists in `backend/app` (much of the provider/config/store refactor is
already implemented; see "status" tags: ✅ done · 🟡 partial · ⬜ to do).

---

## 1. Current Architecture Assessment

**Business flow (preserved):** Vendor PDF upload → identify Spec → vendor OCR →
retrieve Spec → compare → findings. Implemented as a deliberate **two-stage**
flow in `app/services/pipeline_service.py`:

- **Stage 1 `start_upload`** — render → DocLayout → crop → OCR (first pages) →
  LLM metadata extraction (PO/item/material + all declared specs) → spec lookup
  → **pause** at `awaiting_comparison`, write `preview.json`.
- **Stage 2 `start_comparison`** — full OCR → LLM segmentation → evidence-based
  comparison → deterministic cross-document aggregation → `final_report.json`
  (structured) + `final_report.md` (Turkish narrative).

**What is already in place (✅):**
- Provider abstraction: `app/providers/{layout,ocr,llm,spec_store,spec_lookup}`
  with `base.py` interfaces + a `factory.py` selecting by `ACTIVE_*` config.
- OCR is provider-swappable **remote↔local**: `paddleocr_vl` (remote HTTP,
  OpenAI-compatible) and `paddleocr_vl_local` (in-process transformers).
- Layout: `paddlex_doclayout` (PP-DocLayoutV3, local). **Real, verified**: 9–10
  regions on real documents.
- LLM: `openai_compatible` — same provider talks to vLLM/Qwen, Ollama, or Gemini
  by `.env` only. Verified against local Ollama.
- Config layer: `app/core/config.py` (pydantic-settings) + `.env.example`; no
  hardcoded URLs/tokens/paths in business logic.
- Spec store: SQLite behind a `SpecStore` repository interface
  (`providers/spec_store/sqlite_spec_store.py`); Postgres stub present.
- Spec indexing (2B): standalone, hash + revision incremental, section/cross-ref
  parsing, per-spec JSON+MD artifacts, CLI `scripts/index_specs.py`.
- Spec lookup (Section 3 seam): `sap_then_local_lookup` chains SAP → store exact
  → fuzzy → single-file index → structured error.
- SAP abstraction: `SpecSource` ABC with `SapSpecSource` (real) and
  `LocalSpecSource` (dev), selected by `SPEC_SOURCE`.
- Structured findings + UI-shaped report, frontend contract verified (26 unit
  tests + 14 endpoint checks).

**Verified runtime:** Python 3.12 venv, `paddlepaddle 3.3.1` + `paddlex`,
`torch 2.12` + `transformers==4.55.0` (pinned — see Risks). DocLayout and
PaddleOCR-VL both run locally; PaddleOCR-VL extracts real text on CPU but slowly
(~60–90 s/region on 12 MP input), which directly motivates the service split.

---

## 2. Architectural Problems (current weak areas)

| # | Problem | Evidence | Severity |
|---|---|---|---|
| P1 | **OCR is in-process & sequential per page** | `ocr_pipeline.run` loops pages serially; only region-level threading | High (throughput) |
| P2 | **Layout model runs in the app process** (thread-affine singleton) | `layout_detector.py` `_paddle_executor` | High (scaling/coupling) |
| P3 | **No page-level persisted JSON** for multi-page docs | only per-run region dump | Medium (30-page req) |
| P4 | **No job queue / async worker** — pipeline runs in a daemon `threading.Thread` | `pipeline_service` | High (scale) |
| P5 | **Two storage designs** (file-based live + unused SQLAlchemy) | `app/db/*` unwired | Medium (clarity) |
| P6 | **No batch GPU inference** — one region per request | provider `recognize(bytes)` | High (GPU cost) |
| P7 | **No streaming for large PDFs** — full doc rendered in loop | `fitz.open` whole file | Medium (memory) |
| P8 | **transformers pin (4.55) for local OCR** is fragile | model remote code | Medium (maintenance) |
| P9 | **Scheduler not wired** — spec indexing is CLI-only | `schedule_spec_indexing.py` is a cron entry, no live scheduler | Low (ops) |
| P10 | **SAP provider naming** doesn't match target (`Mock/RealSAPProvider`) | `spec_sources/*` | Low (cosmetic) |

---

## 3. Refactoring Plan (incremental, flow-preserving)

Ordered to avoid breaking the working flow:

1. **Extract OCR + layout into HTTP services** behind the existing provider
   interfaces (no business-logic change). The app keeps calling
   `get_ocr_provider().recognize(...)`; only the provider implementation becomes
   a remote client. (P1, P2, P6)
2. **Introduce a job queue** (Celery/RQ/Arq) for the vendor pipeline; the current
   `threading.Thread` body becomes a task. `run_id` already models a job. (P4)
3. **Add page-level + document-level JSON** persistence in `storage_service`. (P3)
4. **Add a batch OCR endpoint** to the OCR service (`recognize_batch`) and a
   provider method; the pipeline sends a page's crops as one batch. (P6)
5. **Stream PDF pages** (render page N, process, release) instead of holding all
   pixmaps. (P7)
6. **Rename SAP providers** to `RealSAPProvider`/`MockSAPProvider` (keep
   `SpecSource` ABC). (P10)
7. **Wire a scheduler** (APScheduler in-app or external cron calling the CLI). (P9)
8. **Decide one source of truth** for runs/findings: keep file-based for now,
   formalize the repository so Postgres is a drop-in. (P5)

---

## 4. Target Production Architecture

```
                       ┌─────────────────────────┐
   React Frontend ───▶ │  Application Backend     │  (FastAPI, stateless, N replicas)
   (frozen /api/*)     │  - routes / orchestration│
                       │  - provider clients      │
                       └───────────┬──────────────┘
                                   │ enqueue job (run_id)
                                   ▼
                       ┌─────────────────────────┐
                       │  Job Queue + Workers     │  (Celery/RQ, async)
                       │  - vendor pipeline tasks │
                       │  - spec indexing tasks   │
                       └───┬───────────────┬──────┘
              HTTP (batch) │               │ HTTP (batch)
                           ▼               ▼
              ┌────────────────┐  ┌────────────────────┐
              │ DocLayout Svc  │  │ PaddleOCR-VL Svc    │   (H200, long-lived,
              │ PP-DocLayoutV3 │  │ OpenAI-compatible   │    queue-batched, autoscale)
              └────────────────┘  └────────────────────┘
                           │               │
                           ▼               ▼
              ┌──────────────────────────────────────┐
              │ Storage Layer (repository pattern)    │
              │ SQLite → PostgreSQL/pgvector/OpenSearch│
              │ + object store for artifacts (S3/MinIO)│
              └──────────────────────────────────────┘
                                   │
                                   ▼
                       ┌─────────────────────────┐
                       │  Comparison Engine (LLM) │  (vLLM/Qwen or Gemini)
                       └─────────────────────────┘
```

Key property: the app never imports a model. Every model is reached through a
provider client configured by `.env`. Swapping PaddleOCR-VL → Qwen-OCR/MinerU/
Gemini/Azure = new provider class + `ACTIVE_OCR_PROVIDER` change.

---

## 5. Service Boundaries

- **Application Backend** — HTTP API (the frozen `/api/*` contract), request
  validation, orchestration, persistence, comparison prompting. Stateless,
  horizontally scalable.
- **DocLayout Service** — input: page image; output: regions (bbox/type/score).
  Stateless model server (PaddleX serving / Triton / custom FastAPI). Batchable.
- **PaddleOCR-VL Service** — input: region image(s) + task; output: text/markdown
  + confidence. OpenAI-compatible chat-completions. Batched, queue-fronted.
- **LLM Service** — vLLM/Qwen (or Gemini) for metadata/segmentation/comparison.
- **Spec Indexing Worker** — scheduled, separate lifecycle from the request path.
- **Storage** — relational (runs/findings/specs) + object store (PDFs, crops,
  JSON/MD artifacts).

Boundary rule already enforced in code: services depend on provider **interfaces**
(`OcrProvider`, `LayoutProvider`, `LlmProvider`, `SpecStore`,
`SpecLookupStrategy`), never on concrete models.

---

## 6. Database Design (repository pattern)

Today: file-based job artifacts under `data/output/run_<id>/` + SQLite spec
store. Target relational schema (the unused `app/db/models.py` already sketches
most of it — formalize and wire behind repositories):

- `runs(id, po_number, po_item, material, status, current_step, progress,
  created_at, finished_at, inspector_id)`
- `documents(id, run_id, kind[vendor|spec], filename, page_count, pdf_uri)`
- `pages(id, document_id, page_number, image_uri, ocr_json_uri)`
- `regions(id, page_id, region_id, type, bbox, text, confidence, crop_uri,
  needs_review)`
- `segments(id, run_id, doc_type, page_range, metadata)`
- `findings(id, run_id, segment_id, finding_id, parameter, result, severity,
  spec_section, spec_evidence, vendor_page, vendor_region_ids, vendor_evidence,
  rationale, effective_result)`
- `overrides(id, finding_id, action, new_status, note, inspector_id, created_at)`
- `specs(id, spec_no, revision, file_path, content_hash, modified_time, status,
  text, output_json_uri, output_md_uri, indexed_at)` — **implemented in SQLite**
- `spec_sections`, `spec_references` — **implemented**

Migration path: `SpecStore` interface is done; add `RunRepository` /
`FindingRepository` interfaces with a SQLite impl now and a Postgres impl later.
pgvector/OpenSearch slot in as an optional `SpecSearchIndex` provider (the
current `search()` is normalized-name + rapidfuzz; vector is additive).

---

## 7. OCR Pipeline Design

Per page (target):
1. Render page at `PDF_RENDER_DPI` (stream one page at a time — P7 fix).
2. DocLayout service → regions (bbox in pixel space; **crop fix already applied**
   in `ocr_pipeline._crop_region`, pixel→point).
3. **Batch** all region crops of the page → one OCR-service call
   (`recognize_batch`, `OCR_MAX_CONCURRENCY` / batch size from config).
4. IoU dedup (`dedup_service`, thresholds from config) → before/after counts.
5. Persist **page-level JSON** (`pages.ocr_json_uri`) immediately (resumable),
   then **document-level JSON** + **Markdown** at the end.
6. 30-page requirement: every page completes and is stored before comparison is
   allowed (frontend already gates compare behind pipeline completion).

Anti-hallucination + JSON repair already enforced in the four prompt files and
`json_utils`.

---

## 8. Spec Indexing Design

Implemented and runnable (`scripts/index_specs.py`):
- Discover spec PDFs under `SPEC_NETWORK_ROOT` (local mock now, UNC later).
- Per file: content hash + revision + mtime.
- Skip if hash & revision unchanged (`SPEC_REINDEX_IF_*` flags); reindex on change.
- Native-text-first extraction, OCR fallback (`spec_ocr_pipeline_service`).
- Parse sections/clauses + detect cross-references (with indexed flag).
- Write to SQLite store + per-spec JSON/MD.

To add: live **scheduler** (APScheduler job calling `SpecIndexingService.run`
on `SPEC_INDEX_SCHEDULE` cron) and a `/api/spec-index/status/{run_id}` for async
runs (CLI is synchronous today).

---

## 9. Performance Optimization Plan

- **Parallelism**: move from per-page-serial to (a) page-level parallelism via
  the job queue, and (b) region **batching** to the OCR service. `OCR_MAX_CONCURRENCY`
  already config-driven.
- **GPU utilization**: long-lived OCR/layout services (no per-request model load
  — currently the local provider loads once via singleton, which is the right
  pattern to preserve in the service); queue-based **dynamic batching** (e.g.
  vLLM continuous batching for the OCR-VL decoder, Triton dynamic batching for
  DocLayout).
- **Memory**: stream pages (render→process→free); cap `OCR_LOCAL_MAX_PIXELS`
  (already config) and `max_new_tokens`; never hold all pixmaps. For very large
  PDFs, process in page windows.
- **Caching**: spec OCR cached by hash (done); vendor crops cached by page hash
  to allow resume.
- **Measured reality**: PaddleOCR-VL on CPU ≈ 60–90 s/region → a 10-region page
  ≈ 10–15 min. On H200 with batching this drops by orders of magnitude; this is
  exactly why OCR must be a remote batched service, not in-process.

---

## 10. Deployment Architecture

- **App backend**: Docker image, N stateless replicas behind a load balancer.
- **OCR/Layout/LLM**: separate GPU deployments (H200), each its own image +
  autoscaling; exposed as internal HTTP. TLS/mTLS already supported
  (`TLS_*` config, `clients/http.py`).
- **Workers**: queue consumers (same image, different entrypoint).
- **Storage**: managed Postgres + object store; SQLite only for dev.
- **Config**: 12-factor — env vars in prod, `.env` in dev, optional YAML overlay
  (see §11).
- **Observability**: structured logging exists (`core/logging.py`); add metrics
  (per-stage latency, OCR queue depth) and the consistent error shape
  (`core/errors.py`, stage enum) is already wired.

### GPU environment recommendations (dev/test for PaddleOCR-VL 1.6)

| Option | Best for | Notes |
|---|---|---|
| **Modal** | Easiest serverless GPU; spin up an OCR endpoint in minutes | Per-second billing, A10/A100/H100; great for a `paddleocr_vl` remote provider during dev |
| **RunPod** | Cheapest persistent/on-demand pods; community H100 | Good price/perf; expose the OCR service over HTTPS; supports templates |
| **Vast.ai** | Lowest cost spot GPUs for bulk/batch indexing | Variable reliability; ideal for one-off spec re-indexing jobs |
| **Lambda Labs** | Stable on-demand H100/H200-class for realistic perf tests | Closest to the production H200 profile |
| **Local Docker** | CI / contract tests / small docs | Use the in-process `paddleocr_vl_local` provider or a CPU container; slow but free |

Recommended path: develop against **Modal or RunPod** running PaddleOCR-VL as an
OpenAI-compatible endpoint, point `OCR_SERVICE_URL` at it, set
`ACTIVE_OCR_PROVIDER=paddleocr_vl`. Validate H200-like throughput on **Lambda**
before production. Keep `paddleocr_vl_local` for offline/CI correctness checks.

---

## 11. Configuration Strategy

Single source of truth: `app/core/config.py` (pydantic-settings), sourced from
env / `.env` (`.env.example` is the template; no real secrets). Everything is
already config-driven: model URLs, paths, bearer/basic auth scheme, GPU device,
OCR pixels/tokens, dedup thresholds, concurrency, DB URL, spec fuzzy threshold,
hash algorithm, reindex flags, TLS.

Enhancements:
- Optional **YAML overlay** loaded by `config.py` for non-secret structured
  config (per-environment), env vars still win (precedence: env > .env > YAML >
  defaults).
- `ACTIVE_*` selectors stay the single switch for swapping providers.
- Add a `config doctor` script that validates required keys per `ACTIVE_*`
  selection (e.g. remote OCR requires `OCR_SERVICE_URL`).

---

## 12. Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| **transformers 4.55 pin** for local OCR | Future dep conflicts | Keep local OCR isolated (its own service/venv); prefer the **remote** provider in prod so the app venv isn't pinned |
| **CPU OCR too slow** for real docs | Unusable locally | Remote GPU service + batching; local provider only for CI/spot checks |
| **SAP endpoint unavailable** | Can't test real lookup | `MockSAPProvider` via config (exists as `LocalSpecSource`); formalize naming |
| **In-process model coupling** | Hard to scale | Service extraction behind existing provider interfaces |
| **Single-threaded job runner** | No concurrency/durability | Job queue; `run_id` already the job key |
| **File + DB dual storage drift** | Confusion | Pick repository-backed store; keep file artifacts as object-store blobs |
| **Large PDF memory** | OOM | Streaming page processing |
| **LLM hallucination** | Wrong findings | Already mitigated: evidence-required prompts, UNCLEAR default, deterministic aggregation |

---

## 13. Missing Components (gap list)

- ⬜ Remote DocLayout HTTP service + `paddlex_doclayout_remote` provider.
- ⬜ OCR **batch** endpoint + `recognize_batch` provider method.
- ⬜ Job queue + worker entrypoint (vendor pipeline + spec indexing as tasks).
- ⬜ Page-level & document-level JSON persistence (currently per-run regions).
- ⬜ Live scheduler for spec indexing (CLI exists).
- ⬜ `RunRepository`/`FindingRepository` (relational) behind interfaces.
- ⬜ Object storage adapter (S3/MinIO) for PDFs/crops/artifacts.
- ⬜ `/api/spec-index/status/{run_id}` async status; `cancel-processing` without
  run_id (frontend calls it in one place).
- ⬜ Metrics/tracing.
- 🟡 Streaming PDF rendering (works, not yet windowed).
- 🟡 SAP provider rename to Real/Mock.

---

## 14. Recommended Folder Structure (evolution, not rewrite)

```
backend/
├── app/
│   ├── core/            {config, logging, errors, constants, database}
│   ├── api/v1/          routes_* (frozen /api/* contract)
│   ├── providers/       layout/ ocr/ llm/ spec_store/ spec_lookup/  + factory
│   │   └── sap/         RealSAPProvider, MockSAPProvider (move spec_sources here)
│   ├── services/        pipeline (vendor 2A), spec_indexing (2B), dedup,
│   │                    metadata_extraction, comparison, aggregation,
│   │                    report_renderer, storage, spec_* 
│   ├── repositories/    (new) run_repo, finding_repo behind interfaces
│   ├── workers/         (new) queue tasks: vendor_pipeline_task, spec_index_task
│   ├── prompts/         metadata_extraction, segmentation, segment_comparison,
│   │                    final_aggregation
│   ├── schemas/ utils/
├── services/            (new) deploy units:
│   ├── doclayout_service/    FastAPI + PP-DocLayoutV3
│   └── paddleocr_vl_service/ FastAPI/vLLM, OpenAI-compatible
├── scripts/             download_models, index_specs, schedule_spec_indexing,
│                        test_sap_spec, test_full_pipeline, e2e_scanned_pdf
├── tests/  models/  data/
├── requirements.txt  requirements-ml.txt  .env.example  README.md
```

---

## 15. Detailed Implementation Roadmap

**Phase 0 — done this session (✅):** provider pattern, config layer, SQLite spec
store + indexing + lookup chain, structured findings + UI-shaped report, frontend
contract verified, real DocLayout + PaddleOCR-VL running locally, mocks removed.

**Phase 1 — Service extraction (1–2 wk):**
- Stand up DocLayout + PaddleOCR-VL as HTTP services (Modal/RunPod).
- Add `paddleocr_vl` remote already exists; add `doclayout_remote` provider.
- Switch dev to remote OCR (`ACTIVE_OCR_PROVIDER=paddleocr_vl`), validate parity
  with the local provider on the sample docs.

**Phase 2 — Throughput (1–2 wk):**
- Job queue + worker; convert the two pipeline stages to tasks.
- OCR batch endpoint + `recognize_batch`; page-level parallelism.
- Page-level/document-level JSON persistence; resumable runs.

**Phase 3 — Storage & scale (1–2 wk):**
- `RunRepository`/`FindingRepository` (SQLite now), Postgres impl; object store
  adapter; migrate artifacts to blobs.
- Live scheduler for spec indexing + async status endpoint.

**Phase 4 — Hardening (ongoing):**
- Metrics/tracing, autoscaling policies, GPU batching tuning, config doctor,
  SAP provider rename, load tests on H200-class (Lambda).

**Acceptance gates per phase:** existing 26 unit tests + the frontend contract
test stay green; `e2e_scanned_pdf.py` passes against the active providers.
