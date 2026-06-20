# Phase 1 — Final Report

Goal: only **DocLayout** runs locally; **PaddleOCR-VL** and the **LLM** run on
remote GPU, reached by URL + bearer token, swappable by configuration only.
This was implemented against the existing codebase (no rewrite).

---

## 1. Files changed / added

**Config & clients**
- `app/core/config.py` — production key names with backward-compatible aliases
  (`OCR_SERVICE_BEARER_TOKEN`, `OCR_BATCH_SIZE`, `LLM_SERVICE_URL`,
  `LLM_SERVICE_BEARER_TOKEN`, `LLM_MODEL_NAME`, `REQUEST_TIMEOUT`, `RETRY_COUNT`,
  `MAX_CONCURRENCY`, `CIRCUIT_BREAKER_*`, `SPEC_LOOKUP_URL`, `NETWORK_SHARE_PATH`,
  `STORAGE_PATH`); optional `config.yaml` overlay (env > .env > yaml > defaults).
- `app/services/clients/http.py` — `post_json` with retries + exponential backoff,
  per-host circuit breaker, timeout, TLS/mTLS, token-safe logging.
- `app/services/clients/llm_client.py` — routed through `post_json`.
- `app/services/ocr/ocr_engine.py` — `post_json`, `recognize_batch` (bounded
  concurrency, per-region failure isolation), config-driven auth.
- `app/providers/ocr/base.py`, `paddleocr_vl_provider.py` — `recognize_batch`.
- `app/services/ocr/ocr_pipeline.py` — batch a page's regions through the provider.

**Services & deploy**
- `services/paddleocr_vl_service/app.py` — OpenAI-compatible OCR service (+health).
- `colab/paddleocr_vl_server.py` + `colab/README.md` — Colab GPU deployment.

**API / storage / health**
- `app/api/v1/routes_health.py` — `/api/v1/health` + `/health/ready` (probes).
- `app/services/storage_service.py` — `save_ocr_pages` (page + document JSON, v1.0).
- `app/services/pipeline_service.py` — wired page-level JSON in both stages.
- `.env` (remote-only) + `.env.example` (production keys + resilience).

**Tests**
- `tests/test_resilient_client.py`, `tests/test_ocr_engine.py`,
  `tests/test_ocr_service.py`, `tests/test_provider_switching.py`.

---

## 2. Bugs fixed (this phase + earlier, still relevant)
- OCR auth header was hardcoded bearer → now config-driven (bearer|basic).
- No retry/timeout/breaker on remote calls → added (transient failures recovered).
- One bad region could sink a page → `recognize_batch` isolates per-region errors.
- `/api/report/{id}` returned markdown, frontend needed structured findings → fixed
  (carried from the contract fix; still green).
- review-regions returned an object, frontend reads an array → fixed.
- No page-level OCR JSON for multi-page docs → added.

---

## 3. Architecture improvements
- **Service separation**: OCR + LLM are remote OpenAI-compatible services; only
  DocLayout is local. The app imports no heavy model.
- **Resilience**: retries, backoff, circuit breaker, timeouts, structured logging.
- **Batching**: page regions sent concurrently to the OCR service (`OCR_BATCH_SIZE`).
- **Config-only swapping**: `ACTIVE_*` selectors + aliases; OCR/LLM/spec-store/
  spec-lookup/SAP all interchangeable without code edits.
- **Readiness**: `/health/ready` gates traffic on remote-service reachability.
- **Versioned output**: page-level + document-level JSON (schema 1.0).

---

## 4. Required environment variables
Minimum to run remote-only (fill tunnel URLs from Colab):
```dotenv
ACTIVE_LAYOUT_PROVIDER=paddlex_doclayout
LAYOUT_DEVICE=cpu
ACTIVE_OCR_PROVIDER=paddleocr_vl
OCR_SERVICE_URL=https://<ocr-tunnel>.trycloudflare.com
OCR_RECOGNIZE_PATH=/v1/chat/completions
OCR_SERVICE_BEARER_TOKEN=...
OCR_MODEL_NAME=paddleocr-vl-16
OCR_BATCH_SIZE=4
ACTIVE_LLM_PROVIDER=openai_compatible
LLM_SERVICE_URL=https://<llm-tunnel>.trycloudflare.com/v1
LLM_SERVICE_BEARER_TOKEN=...
LLM_MODEL_NAME=Qwen/Qwen2.5-3B-Instruct
RETRY_COUNT=3
REQUEST_TIMEOUT=120
SPEC_SOURCE=local
NETWORK_SHARE_PATH=data/spec_store/mock_specs
```
Full list + aliases in `.env.example`.

---

## 5. Deployment instructions
**Backend (local, DocLayout only):**
```bash
cd backend && python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt   # paddle for layout
python scripts/download_models.py                        # PP-DocLayoutV3 only
cp .env.example .env                                     # set the tunnel URLs
uvicorn app.main:app --port 8002
```
**Remote OCR + LLM (Colab GPU):** follow `backend/colab/README.md` — run the
PaddleOCR-VL server + a Qwen vLLM server, expose each via cloudflared, paste the
two HTTPS URLs + tokens into `.env`. Production: deploy the same OCR service image
on H200 behind a stable URL; point `OCR_SERVICE_URL` at it.

---

## 6. Test results
`python -m pytest tests/ -q` → **41 passed**. Coverage includes: PO zero-pad, IoU/
dedup, JSON repair, mocked SAP, spec hash/revision, report contract + status
mapping, **resilient client (retry/exhaust/circuit-breaker)**, **OCR engine wire
contract + batch isolation + auth**, **OCR service (parse/auth/400)**, **provider +
config switching + production aliases**.

Real HTTP loopback (model stubbed, everything else real): `OcrEngine` → live
OpenAI-compatible endpoint → single + batch recognize OK; wrong token → retries →
`RemoteServiceError`. Earlier this session: real DocLayout (9–10 regions on real
docs) and real PaddleOCR-VL text extraction were both verified.

---

## 7. Benchmark results
Measured (this MacBook, CPU — dev only):
- DocLayout PP-DocLayoutV3: ~3 s/page (model load ~10 s once).
- PaddleOCR-VL on CPU: ~60–90 s/region; clean text ~94 s incl. load. A 10-region
  page ≈ 10–15 min → **CPU is not viable for real docs** (the reason for remote GPU).

Projected (remote, not yet measured here — validate on the chosen provider):
- PaddleOCR-VL 0.9B on T4/A10: ~0.5–2 s/region; on A100/H100: sub-second with
  batching. A 30-page doc should drop from hours (CPU) to a few minutes (GPU).

---

## 8. Recommended GPU provider — infrastructure investigation

| Provider | GPUs / VRAM | Est. cost | Deploy ease | OpenAI API | PaddleOCR-VL | Multimodal LLM | Batch OCR | Production |
|---|---|---|---|---|---|---|---|---|
| **Google Colab Pro/Pro+** | T4/L4/A100 40GB; 15–40GB | ~$10–50/mo | Easy (notebook) | via our wrapper/vLLM | ✅ (T4 ok) | ✅ small/med | ⚠ session limits | ❌ ephemeral |
| **Modal** | T4→H100; up to 80GB | per-sec, ~$2–4/hr H100 | Very easy (py deco) | vLLM/custom | ✅ | ✅ | ✅ autoscale | ✅ serverless |
| **RunPod** | A100/H100/H200; 40–141GB | ~$2–4/hr H100, cheaper community | Easy (templates) | vLLM image | ✅ | ✅ | ✅ | ✅ pods/serverless |
| **Lambda Labs** | A100/H100/H200; 40–141GB | ~$2–3/hr on-demand | Medium (VM) | vLLM | ✅ | ✅ | ✅ | ✅ stable |
| **Vast.ai** | broad, spot | cheapest (~$1/hr H100 spot) | Medium | vLLM | ✅ | ✅ | ✅ bulk | ⚠ spot reliability |
| **HF Inference Endpoints** | T4→A100/H100 | per-hr managed | Very easy | ✅ native | ⚠ custom handler | ✅ | ⚠ | ✅ managed |
| **Together AI** | hosted | per-token | Trivial (key) | ✅ native | ❌ (their catalog) | ✅ Qwen etc. | n/a | ✅ for LLM |
| **Fireworks AI** | hosted | per-token | Trivial (key) | ✅ native | ❌ | ✅ | n/a | ✅ for LLM |

Recommendations:
1. **Local development testing** → **Google Colab (free/Pro)** for OCR+LLM via
   cloudflared (this phase) — zero cost, real GPU.
2. **Pre-production validation** → **Modal** or **RunPod** (persistent HTTPS,
   autoscaling, OpenAI-compatible, closest workflow to prod).
3. **Production deployment** → **RunPod or Lambda** H100/H200 dedicated for OCR;
   **Together/Fireworks** (or self-host vLLM) for the LLM.
4. **Lowest cost** → **Vast.ai** spot for bulk/offline (spec re-indexing); Colab free for dev.
5. **Closest to H200 production** → **Lambda Labs** (H200/H100 on-demand) or RunPod H200.

The architecture switches between all of these by `.env` only.

---

## 9. Recommended production configuration
- OCR: dedicated **H200** running the `paddleocr_vl_service` (or vLLM-served VLM),
  `OCR_BATCH_SIZE=8–16`, `MAX_CONCURRENCY` tuned to GPU; mTLS on (`TLS_*`).
- LLM: vLLM Qwen2.5-32B/72B (or managed Together/Fireworks), `REQUEST_TIMEOUT=120`,
  `RETRY_COUNT=3`, circuit breaker on.
- DocLayout: local CPU per app replica (small model) or its own small service.
- Storage: PostgreSQL (`DATABASE_URL`) + S3/MinIO for artifacts; SQLite for dev.
- App: N stateless replicas, behind LB using `/health/ready`.
- Spec indexing: scheduled (cron/APScheduler) calling `scripts/index_specs.py`.

---

## 10. Phase 2 roadmap
1. **Job queue** (Celery/RQ/Arq): convert the two pipeline stages to durable tasks;
   add Submit/Status/Result/Cancel as first-class job APIs + dead-letter handling.
2. **DocLayout as a service** + `doclayout_remote` provider (optional; keep local default).
3. **Relational repositories** (`RunRepository`/`FindingRepository`) with SQLite +
   PostgreSQL impls; migrate run artifacts to an **object-storage** adapter (S3/MinIO).
4. **True batch OCR endpoint** (multi-image per request) on the GPU service; dynamic
   batching (vLLM/Triton) for max GPU utilization.
5. **Scheduler** for spec indexing + `/api/spec-index/status/{run_id}` async status.
6. **Streaming** large PDFs (page-window rendering) to cap memory.
7. **Observability**: metrics (per-stage latency, OCR queue depth), tracing, error tracking.
8. **SAP**: formalize `RealSAPProvider`/`MockSAPProvider` naming; integrate the real
   endpoint when access is available.
9. **Load tests** on H200-class hardware; tune batch/concurrency; cost model.
