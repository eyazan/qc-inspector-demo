# QC Inspector — Backend

FastAPI backend for the QC Inspector. Two independent pipelines share services
but run as separate subsystems:

- **2A Vendor pipeline** (foreground, user-triggered): upload → render → local
  layout (PP-DocLayoutV3) → crop → remote OCR (PaddleOCR-VL) → IoU dedup →
  LLM metadata → spec lookup → LLM segmentation → evidence-based comparison →
  cross-document aggregation → structured `final_report.json` + Turkish
  `final_report.md` narrative.
- **2B Spec indexing pipeline** (background, CLI/scheduled): discover spec PDFs →
  hash/revision skip → native-first / OCR-fallback text → parse sections +
  cross-references → SQLite spec store + per-spec JSON/MD artifacts.

## Execution topology

- **This machine (MacBook, CPU):** runs the API and **local** layout detection.
- **Remote GPU host:** runs PaddleOCR-VL (OCR) — always a remote HTTP call here.
- **Remote vLLM:** runs the Qwen LLM — also remote.

Every machine-specific value (URLs, tokens, model paths, cache dirs) lives in
`.env` only. Moving to another machine = edit `.env`, never source.

## Setup

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # core API + mock providers
# Optional, only on the machine that runs LOCAL layout detection:
pip install -r requirements-ml.txt        # paddlepaddle + paddlex
cp .env.example .env                       # then fill in real values
```

Pull the layout model on demand (config-driven repo/dir, nothing hardcoded):

```bash
python scripts/download_models.py          # PP-DocLayoutV3 -> LAYOUT_MODEL_DIR
```

## Run the API

```bash
uvicorn app.main:app --reload --port 8002
```

The frontend (CRA) talks to `http://localhost:8002` over the flat `/api/*`
contract (e.g. `/api/upload`, `/api/start-full-pipeline`,
`/api/processing-status/{run_id}`, `/api/report/{id}`,
`/api/report/{id}/review-regions`, `/api/report/{id}/pdf`,
`/api/findings/{id}/override`). Do not change these — the frontend is frozen.

### Offline / mock mode

Set `RUN_MODE=mock` (or any `ACTIVE_*_PROVIDER=mock`) to run the whole pipeline
with no GPU/SAP/LLM/OCR reachable — useful for local smoke tests:

```bash
RUN_MODE=mock uvicorn app.main:app --port 8002
```

## Vendor pipeline (2A) — smoke test

```bash
RUN_MODE=mock python scripts/test_full_pipeline.py
```

Builds a vendor PDF from `data/samples/*.jpg` (the supplied vendor photos,
HEIC→JPEG converted), runs Stage 1 (upload→preview→pause) then Stage 2
(comparison→aggregation), and prints the structured report + Turkish narrative.
Vendor uploads accept **PDF or image** (JPEG/PNG/TIFF…); images are normalized
to a single-page PDF on upload.

## Spec indexing pipeline (2B) — CLI

```bash
python scripts/index_specs.py --mode full           # (re)index everything
python scripts/index_specs.py --mode incremental     # only new/changed (hash+rev)
python scripts/index_specs.py --spec-name AMS4911     # one spec by name
python scripts/schedule_spec_indexing.py             # cron/Airflow entry point
```

Source root is `SPEC_NETWORK_ROOT` (a local mock folder now:
`data/spec_store/mock_specs/`; a real UNC path later, no code change). Output:
SQLite store at `SPEC_STORE_DB_PATH` + per-spec JSON/MD under `SPEC_OUTPUT_DIR`.

Spec lookup (the seam between 2A and 2B), default `sap_then_local_store`:

```bash
RUN_MODE=mock python scripts/test_sap_spec.py
```

chains SAP → local store exact → fuzzy → on-demand single-file index → clear
structured error.

## Tests

```bash
python -m pytest tests/ -q
```

Covers PO item zero-padding, IoU/dedup, JSON repair, mocked OCR/LLM providers,
mocked SAP client, and spec hash/revision change detection.

## Configuration & providers

All settings are in `app/core/config.py` (sourced from `.env`). Swap a
model/provider via config only:

| Setting | Choices |
|---|---|
| `ACTIVE_LAYOUT_PROVIDER` | `paddlex_doclayout` \| `mock` |
| `ACTIVE_OCR_PROVIDER` | `paddleocr_vl` \| `mock` |
| `ACTIVE_LLM_PROVIDER` | `openai_compatible` \| `mock` |
| `ACTIVE_SPEC_STORE` | `sqlite` \| `postgres` (stub) |
| `ACTIVE_SPEC_LOOKUP_STRATEGY` | `sap_then_local_store` |

## Layout / structure notes

- `app/providers/{layout,ocr,llm,spec_store,spec_lookup}` — provider pattern.
- `backend/_legacy/` — quarantined dead modules (old local-OCR experiment, old
  async OCR design) kept for reference; nothing in `app/` imports them.
- The SQLAlchemy layer under `app/db` + `app/core/database.py` is the documented
  **future Postgres path**; the live vendor flow is file-based under
  `data/output/run_<ts>/` (job-scoped).
