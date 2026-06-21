# QC Inspector — OCR Vendor/Spec Production Runbook

Single source of truth for running the platform locally and deploying it to the
company environment. The system is fully config-driven: moving from local to the
company GPU environment requires editing `.env` only (URLs, tokens, certificate
paths, network paths) — no code changes, no mocks, no hardcoded values.

---

## 1. Current architecture

```
React Frontend ─HTTP /api/*─▶ FastAPI Backend ──┬─ DocLayout (LOCAL, CPU/paddlex)
   (upload, status,           (orchestration,   │
    preview, report)           job lifecycle)   ├─ PaddleOCR-VL  (REMOTE GPU, OpenAI-compatible HTTP)
                                                 ├─ LLM (Qwen-class) (REMOTE GPU, OpenAI-compatible HTTP)
                                                 ├─ SAP/spec lookup service (REMOTE HTTP)
                                                 ├─ Spec store (SQLite → Postgres)
                                                 └─ Object/file store (local FS → S3/MinIO)
```

- **Only DocLayout runs locally.** OCR + LLM + SAP are remote services reached by
  URL + bearer token + a per-service CA bundle. Each is a provider behind an
  interface, selected by config (`DOCLAYOUT_PROVIDER`, `OCR_PROVIDER`,
  `LLM_PROVIDER`, `ACTIVE_SAP_PROVIDER`).
- **Two independent pipelines**: Vendor (foreground, user upload) and Spec
  indexing (background, scheduled). They share the OCR/layout/LLM clients but run
  as separate subsystems.

## 2. Local test architecture

DocLayout local (CPU); OCR + LLM remote (e.g. Colab/RunPod GPU for OCR,
OpenRouter/company GPU for LLM); SAP not reachable → the spec-lookup chain
resolves the spec from the LLM-extracted spec name against the locally indexed
spec store. No mocks. Template: `backend/.env.local.test`.

## 3. Company deployment architecture

DocLayout local per app replica; OCR + LLM on the H200 GPU server as internal
HTTPS services (mTLS/CA); SAP/spec lookup is the real internal service; Postgres
for the spec store; S3/MinIO for artifacts. Template:
`backend/.env.production.example`. App replicas are stateless behind a load
balancer using `/health/ready`.

## 4. Backend / frontend flow

1. Frontend `POST /api/upload` (vendor PDF) then `POST /api/start-full-pipeline`
   with PO/item/material/inspector_id → returns `run_id`.
2. Frontend polls `GET /api/processing-status/{run_id}` (is_processing,
   current_step, progress, logs, status).
3. Stage 1 pauses at `awaiting_comparison`; frontend shows the preview
   (`GET /api/spec-preview/{run_id}`): vendor PDF, SAP/spec text, matched spec PDF.
4. `POST /api/start-comparison/{run_id}` → Stage 2; poll to `completed`.
5. `GET /api/report/{run_id}` → structured findings + summary; `/review-regions`,
   `/pdf`, `POST /api/findings/{id}/override`.
6. `GET /api/comparison-results` → job history.

## 5. Vendor upload flow

render page → DocLayout regions → IoU dedup → crop → PaddleOCR-VL (remote) per
region (batched) → metadata extraction (LLM: PO/item/material + all declared
specs) → spec lookup → pause/preview → on compare: full OCR (all pages) →
segmentation (LLM) → evidence-based comparison (LLM) → deterministic
cross-document aggregation → structured `final_report.json` + Turkish narrative
+ PDF. All vendor pages are OCR-processed in Stage 2 (Stage 1 OCRs page 1 only,
for fast PO extraction / preview).

## 6. Spec indexing flow

`scripts/index_specs.py` / scheduled job: scan `SPEC_NETWORK_PATH` → hash +
revision + mtime → skip unchanged → native-text-first / OCR-fallback → parse
sections + cross-references → write SQLite store (`specs`, `spec_sections`,
`spec_references`) + per-spec JSON/MD. Idempotent; incremental.

## 7. SAP / spec lookup flow

`SapThenLocalLookup` (config `ACTIVE_SPEC_LOOKUP_STRATEGY`): SAP fetch (by PO
number / PO item / material / spec name) → normalize → local store exact (reindex
if disk hash changed) → fuzzy (`SPEC_FUZZY_MATCH_THRESHOLD`) → discover+index a
single file on the spec root → SAP text fallback → structured not_found error
(stage `spec_lookup`). SAP supports bearer (`SAP_SPEC_SERVICE_BEARER_TOKEN`) or
Basic auth, per-service CA bundle/verify.

## 8. DocLayout flow

PP-DocLayoutV3 via paddlex, local, thread-affine (single executor). Per page:
render at `PDF_RENDER_DPI` → detect regions (bbox pixel-space, type, score) →
IoU dedup (before/after recorded). Pulled by `scripts/download_models.py`.

## 9. PaddleOCR-VL remote GPU flow

Remote OpenAI-compatible `/v1/chat/completions` (`OCR_REMOTE_BASE_URL` + bearer +
`OCR_REMOTE_CA_BUNDLE`/`OCR_REMOTE_VERIFY_TLS`). Region crops are batched
(`OCR_BATCH_SIZE`/`OCR_MAX_WORKERS`) with retries/backoff/circuit-breaker and
per-region failure isolation. The deployable service is
`services/paddleocr_vl_service` (same image for Colab dev and H200 prod); it
reuses the single loader `app/providers/ocr/paddleocr_vl_local_provider.py`.

## 10. LLM comparison flow

Remote OpenAI-compatible (`LLM_REMOTE_BASE_URL` + model + bearer + CA bundle).
Comparison emits structured findings JSON (result enum + citations: vendor page,
region_ids, evidence, spec section/evidence); aggregation reconciles
deterministically (no hallucination). Raw model outputs flow through JSON repair.

## 11. JSON output structure (per vendor job)

```
<OUTPUT_ROOT>/run_<id>/
├── vendor/
│   ├── pages/page_001/{page_image.png, doclayout.json, regions.json, ocr.json, normalized_segments.json}
│   ├── document.json            # page/region counts summary
│   └── <stem>.json              # flat region list
├── reports/{final_report.json, final_report.md}
├── comparison_result.json       # = final_report (findings, summary, citations, warnings)
├── job_metadata.json            # timings per stage, page/region counts, traceability
├── preview.json, metadata.json
└── pdfs/{vendor/, spec/}
```
Full traceability: each finding cites vendor page → region_id → bbox → OCR text →
spec section/evidence.

## 12. Required env variables

See `backend/.env.production.example` (company) and `backend/.env.local.test`
(local). Key groups: ENVIRONMENT/URLs; DOCLAYOUT/OCR/LLM providers + remote
base URL/bearer/CA bundle/verify; SAP_SPEC_SERVICE_*; SPEC_NETWORK_PATH +
spec store; performance (PAGE_PARALLELISM, *_MAX_WORKERS, OCR_BATCH_SIZE);
resilience (RETRY_COUNT, REQUEST_TIMEOUT, circuit breaker). Config fails fast at
startup if required values are missing in `ENVIRONMENT=production`.

## 13. How to run locally

```bash
# Backend (DocLayout local; OCR/LLM remote)
cd backend && python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt
python scripts/download_models.py                 # PP-DocLayoutV3
cp .env.local.test .env                           # fill OCR/LLM endpoints
python scripts/index_specs.py --mode full         # index local specs
uvicorn app.main:app --port 8002
# Frontend
cd frontend && npm install && npm start           # :3000 -> backend :8002
```
E2E: upload a scanned vendor PDF → enter PO/material → spec resolved from indexed
store → all pages OCR'd on the remote GPU → comparison → report in the UI → JSON
artifacts under `data/output/run_*/`.

## 14. How to switch to company GPU services

Copy `.env.production.example` → `.env`, set `ENVIRONMENT=production`, fill the
internal URLs/tokens, point `*_CA_BUNDLE` at the company CA, set
`SPEC_NETWORK_PATH` and (optionally) `SPEC_INDEX_DB_URL` for Postgres. No code
change. Deploy `services/paddleocr_vl_service` and the LLM (vLLM) on the H200.

## 15. Certificates

One internal CA bundle covers all internal services: set `AI_SERVICE_CA_BUNDLE`
(shared default) and/or per-service `OCR_REMOTE_CA_BUNDLE`,
`LLM_REMOTE_CA_BUNDLE`, `SAP_SPEC_SERVICE_CA_BUNDLE`. Set `*_VERIFY_TLS=true` in
production. mTLS client certs via `TLS_CLIENT_CERT_PATH`/`TLS_CLIENT_KEY_PATH`.
Never commit private keys (gitignored).

## 16. Performance / concurrency tuning

- `PAGE_PARALLELISM=true`, `PAGE_RENDER_MAX_WORKERS` — pages processed
  concurrently (DocLayout serializes itself; remote OCR batches overlap).
- `OCR_MAX_WORKERS`/`OCR_BATCH_SIZE` — region concurrency to the OCR service.
- `DOCLAYOUT_MAX_WORKERS=1` (paddlex thread-affine).
- `SPEC_INDEX_BATCH_SIZE` — spec indexing batch.
- Per-stage timings are logged and stored in `job_metadata.json`.

## 17. Known limitations

- A single very large/dense OCR region can exceed a reverse-proxy edge timeout
  (e.g. cloudflared quick-tunnel ~100s) on slow GPUs; cap `OCR_LOCAL_MAX_NEW_TOKENS`
  or use a stable endpoint (H200) without that cap.
- Free LLM tiers (OpenRouter) rate-limit (429); retries help, company GPU removes it.
- Phone-photos-of-a-monitor inputs make DocLayout pick up screen UI; real scanned
  PDFs are clean. The pipeline degrades gracefully (failed OCR → empty region,
  failed LLM → regex/fallback) without crashing.
- Postgres/Celery providers are interface-ready; SQLite/in-process are the defaults.
- S3/MinIO artifact storage is wired: with `ACTIVE_OBJECT_STORE=s3` every run
  artifact is mirrored to the store and the PDF/report serve+read paths fall back
  to it when a replica lacks the local file — no `/api/*` change. Pure-S3 (no
  local disk) multi-run *history* still needs a shared volume or an
  `ObjectStore.list(prefix)` migration (glob-based listing is FS-bound).

## 18. Troubleshooting checklist

- `GET /health` (liveness), `GET /health/ready` (OCR/LLM reachability),
  `GET /metrics` (counters/latency).
- OCR 5xx/timeout → check `OCR_REMOTE_BASE_URL`, bearer, CA bundle, GPU service up.
- LLM 429 → rate limit; raise `RETRY_COUNT` or use the company LLM.
- TLS errors → wrong/missing `*_CA_BUNDLE` or `*_VERIFY_TLS`.
- Spec not found → run `scripts/index_specs.py`; check `SPEC_NETWORK_PATH`.
- Config errors at startup → fail-fast logs list the missing keys for the
  selected providers.
- Per-stage timings + failures in `job_metadata.json` and backend logs (tokens
  are never logged).
