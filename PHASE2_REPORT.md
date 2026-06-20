# Phase 2 — Report

Production scale-out features, all **additive and config-driven**, with safe
local defaults (no Redis/Postgres/S3/GPU required to run or test). The frozen
`/api/*` frontend contract is untouched.

## Delivered

### 1. Durable job queue + job APIs (P2-1)
- `app/jobs/`: `Job` model + `FileJobStore` (durable JSON records under
  `data/jobs/`, dead-letter retained & inspectable); `JobQueue` interface with
  `InProcessJobQueue` (thread pool, retries to `JOB_MAX_ATTEMPTS`, dead-letter on
  final failure, cooperative cancel); `CeleryJobQueue` stub for the broker drop-in.
- APIs: `POST /api/v1/jobs`, `GET /api/v1/jobs/{id}`, `/result`, `POST /cancel`.
- Spec indexing runs as a job: `POST /api/spec-index/run?async_mode=true` +
  `GET /api/v1/spec-index/status/{run_id}`.
- Config: `ACTIVE_JOB_QUEUE`, `JOB_WORKERS`, `JOB_MAX_ATTEMPTS`.

### 2. Object storage abstraction (P2-2)
- `app/repositories/object_store.py`: `ObjectStore` interface;
  `LocalFsObjectStore` (default, path-traversal guarded); `S3ObjectStore`
  (boto3, MinIO/S3 via `S3_ENDPOINT_URL`). Selected by `ACTIVE_OBJECT_STORE`.
- Complements the existing `SpecStore` repository (SQLite→Postgres drop-in).

### 3. SAP Real/Mock providers (P2-3)
- `app/providers/sap/`: `RealSAPProvider` (SAP endpoint) + `MockSAPProvider`
  (local fixtures + canned spec-code from material) selected by
  `ACTIVE_SAP_PROVIDER` (else derived from `SPEC_SOURCE`). No SAP logic in business
  services; `get_spec_source()` now delegates here (backward compatible).

### 4. Scheduler (P2-3)
- `app/services/scheduler.py`: if `SPEC_INDEX_SCHEDULE` (cron) is set and
  APScheduler is installed, submits a `spec_index` job on schedule; started in the
  app lifespan. External cron + `scripts/schedule_spec_indexing.py` remains valid.

### 5. Observability (P2-3)
- `app/core/metrics.py` (in-process counters/latency) + HTTP middleware adding
  `X-Request-ID`, request/latency/status metrics, structured per-request logs.
- `GET /metrics` (JSON) and `GET /metrics/prometheus` (scrape text).

## Tests
`python -m pytest tests/ -q` → **56 passed**. New: job submit→complete,
failure→retry→dead-letter, cancel, unknown-type reject; object store
put/get/exists/delete + traversal guard; SAP factory selection + mock canned
code; metrics increment + readiness shape + request-id header.

## New env vars
`ACTIVE_JOB_QUEUE`, `JOB_WORKERS`, `JOB_MAX_ATTEMPTS`, `ACTIVE_OBJECT_STORE`,
`S3_BUCKET`, `S3_ENDPOINT_URL`, `ACTIVE_SAP_PROVIDER` (see `.env.example`).
Optional deps: `apscheduler`, `boto3`, `celery[redis]`.

## Remaining for Phase 3
- Relational `RunRepository`/`FindingRepository` (SQLite + Postgres) and migrate
  run artifacts to the object store.
- True multi-image batch endpoint on the GPU OCR service + dynamic batching.
- DocLayout as a remote service (`doclayout_remote` provider).
- Streaming large-PDF page windows; load tests + cost model on H200.
- Wire the vendor pipeline through the job queue (currently its own run_id/state
  flow that the frontend polls; jobs are used for spec indexing today).
