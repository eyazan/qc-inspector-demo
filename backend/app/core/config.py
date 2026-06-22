import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Settings(BaseSettings):
    # Precedence: env > .env > config.yaml > defaults. The YAML file path is
    # QC_CONFIG_YAML or ./config.yaml; it holds non-secret structured overrides.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        yaml_file=os.getenv("QC_CONFIG_YAML", "config.yaml"),
        yaml_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # First source wins: env, then .env, then config.yaml, then defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    app_name: str = "QC Inspector OCR Service"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 8002
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    data_root: Path = Field(
        default=Path("data"), validation_alias=AliasChoices("data_root", "storage_path")
    )
    static_mount_path: str = "/files"

    layout_service_url: str = "http://localhost:8101"
    layout_detect_path: str = "/layout/detect"
    layout_timeout_seconds: int = 1800
    # --- DocLayout LOKAL (PP-DocLayoutV3, paddlex) ---
    layout_model_name: str = "PP-DocLayoutV3"
    layout_model_dir: str = "models/PP-DocLayoutV3_safetensors"
    layout_score_threshold: float = 0.10  # dusuk esik -> daha cok bolge

    # --- OCR (remote service, OpenAI-compatible). New names + legacy aliases. ---
    ocr_service_url: str = Field(
        default="http://localhost:8102",
        validation_alias=AliasChoices("ocr_service_url", "ocr_remote_base_url"),
    )
    ocr_recognize_path: str = "/v1/chat/completions"
    ocr_timeout_seconds: int = Field(
        default=1800, validation_alias=AliasChoices("ocr_timeout_seconds", "ocr_timeout")
    )
    ocr_max_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "ocr_max_concurrency", "max_concurrency", "ocr_max_workers", "ocr_remote_max_concurrency"
        ),
    )
    ocr_batch_size: int = 4
    # Comma-separated DocLayout region types to SKIP OCR for (perf). Default
    # empty -> OCR every region (miss nothing). Operators may set e.g.
    # "figure,image" AFTER confirming such regions carry no text in their docs.
    # Skipped regions still appear in artifacts (empty text); only the remote
    # OCR call is avoided.
    ocr_skip_region_types: str = ""
    ocr_bearer_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "ocr_bearer_key", "ocr_service_bearer_token", "ocr_remote_bearer_token"
        ),
    )
    ocr_model_name: str = "paddleocr-vl-16"

    # --- LLM (remote service, OpenAI-compatible). New names + legacy aliases. ---
    llm_base_url: str = Field(
        default="http://localhost:8000/v1",
        validation_alias=AliasChoices("llm_base_url", "llm_service_url", "llm_remote_base_url"),
    )
    llm_model: str = Field(
        default="qwen3",
        validation_alias=AliasChoices("llm_model", "llm_model_name", "llm_remote_model"),
    )
    llm_api_key: str = Field(
        default="not-needed",
        validation_alias=AliasChoices(
            "llm_api_key", "llm_service_bearer_token", "llm_remote_bearer_token"
        ),
    )
    llm_temperature: float = 0.0
    llm_max_tokens: int = 8192
    llm_no_think_suffix: str = ""
    segmentation_timeout_seconds: int = 600
    comparison_timeout_seconds: int = 600
    aggregation_timeout_seconds: int = 300

    # --- Job queue (async work: vendor pipeline, spec indexing) ---
    active_job_queue: str = "inprocess"          # inprocess | celery
    job_workers: int = 2
    job_max_attempts: int = 3

    # --- Object storage (artifacts: PDFs, crops, JSON/MD) ---
    active_object_store: str = "local"           # local | s3
    s3_bucket: str = ""
    s3_endpoint_url: str = ""                    # MinIO/S3-compatible

    # --- SAP provider selection (real | mock). If unset, derived from spec_source
    # (sap->real, local->mock) by the SAP factory. ---
    active_sap_provider: str = ""

    # --- Resilience (production HTTP clients) ---
    retry_count: int = 3
    retry_backoff_seconds: float = 0.5
    request_timeout_seconds: int = Field(
        default=120, validation_alias=AliasChoices("request_timeout_seconds", "request_timeout")
    )
    circuit_breaker_fail_max: int = 5
    circuit_breaker_reset_seconds: int = 30
    spec_lookup_url: str = ""

    # ==================================================================
    # Company deployment (prompt Section 11): per-service TLS/CA bundle,
    # environment, base URLs, performance. New names alias the existing
    # fields where possible so current code keeps working unchanged.
    # ==================================================================
    environment: str = "local"                 # local | production
    backend_base_url: str = "http://localhost:8002"
    frontend_base_url: str = "http://localhost:3000"
    output_root: Optional[Path] = None         # overrides <data_root>/output if set

    # Shared AI-service TLS default (used when a per-service one is unset)
    ai_service_ca_bundle: Optional[str] = None
    ai_service_verify_tls: bool = True

    # Per-service TLS (CA bundle path + verify flag) — company internal CA
    ocr_remote_ca_bundle: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("ocr_remote_ca_bundle", "ai_service_ca_bundle")
    )
    ocr_remote_verify_tls: bool = Field(
        default=True, validation_alias=AliasChoices("ocr_remote_verify_tls", "ai_service_verify_tls")
    )
    llm_remote_ca_bundle: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("llm_remote_ca_bundle", "ai_service_ca_bundle")
    )
    llm_remote_verify_tls: bool = Field(
        default=True, validation_alias=AliasChoices("llm_remote_verify_tls", "ai_service_verify_tls")
    )
    sap_spec_service_bearer_token: str = ""
    sap_spec_service_ca_bundle: Optional[str] = None
    # SAP spec endpoint does not require certificate verification by default
    # (the company endpoint is reached without a cert). Set
    # SAP_SPEC_SERVICE_VERIFY_TLS=true (and/or SAP_SPEC_SERVICE_CA_BUNDLE) to
    # turn verification back on without any code change.
    sap_spec_service_verify_tls: bool = False

    # Performance / concurrency (prompt Section 8)
    doclayout_max_workers: int = 1             # paddlex is thread-affine -> keep 1
    page_render_max_workers: int = 2
    page_parallelism: bool = True              # OCR pages concurrently
    spec_index_batch_size: int = 8
    spec_index_db_url: str = ""                # optional Postgres URL for spec store

    pdf_render_dpi: int = 150
    borderline_threshold_ratio: float = 0.10

    spec_source_dir: Path = Path("data/specs")

    # --- Spec kaynagi (SAP / local) ---
    spec_source: str = "local"  # "sap" | "local"
    # SAP endpoint: .env'de SAP_SPEC_ENDPOINT veya PO_API_BASE_URL (gercek servis adi)
    sap_spec_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices(
            "sap_spec_endpoint", "po_api_base_url", "sap_spec_service_base_url"
        ),
    )
    sap_spec_read_path: str = Field(
        default="/read-text",
        validation_alias=AliasChoices("sap_spec_read_path", "sap_spec_service_endpoint"),
    )
    sap_spec_timeout_seconds: int = Field(
        default=150,
        validation_alias=AliasChoices(
            "sap_spec_timeout_seconds", "po_api_timeout", "sap_spec_service_timeout_seconds"
        ),
    )
    sap_api_user: str = Field(
        default="", validation_alias=AliasChoices("sap_api_user", "po_api_user")
    )
    sap_api_password: str = Field(
        default="", validation_alias=AliasChoices("sap_api_password", "po_api_password")
    )

    # --- Spec PDF bulma + indeksleme (dosya-tabanli) ---
    # .env'de SPEC_DOCS_UNC_PATH veya SPEC_DOCS_FOLDER (gercek servis adi)
    spec_docs_unc_path: str = Field(
        default="", validation_alias=AliasChoices("spec_docs_unc_path", "spec_docs_folder")
    )
    spec_index_dir: Path = Path("data/specs_index")
    # Spec OCR sayfa siniri YOK (0 -> tum sayfalar). Spec dokumaninin TAMAMI
    # OCR'lanir; aktif spec pipeline'i zaten tum sayfalari isler.
    spec_ocr_max_pages: int = 0             # 0 -> tum sayfalar

    # --- Iki asamali akis ---
    # Bu sinir SADECE Asama-1 onizleme/PO okumasi icindir (preview mantigi).
    # Asama-2 (karsilastirma) ve spec indeksleme TUM sayfalari OCR'lar, sinir YOK.
    # 0 -> Asama-1 de tum sayfalari OCR'lar (onizleme yavaslar).
    upload_ocr_max_pages: int = 1           # 0 -> tum sayfalar (sadece onizleme)

    tls_ca_cert_path: Optional[Path] = None
    tls_client_cert_path: Optional[Path] = None
    tls_client_key_path: Optional[Path] = None
    tls_verify: bool = True

    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Provider selection (Section 6) — swap a model/provider via .env only.
    # ------------------------------------------------------------------
    active_layout_provider: str = Field(
        default="paddlex_doclayout",
        validation_alias=AliasChoices("active_layout_provider", "doclayout_provider"),
    )
    # paddleocr_vl (remote GPU service) | paddleocr_vl_local (local in-process)
    active_ocr_provider: str = Field(
        default="paddleocr_vl",
        validation_alias=AliasChoices("active_ocr_provider", "ocr_provider"),
    )
    # openai_compatible (remote GPU/LLM service)
    active_llm_provider: str = Field(
        default="openai_compatible",
        validation_alias=AliasChoices("active_llm_provider", "llm_provider"),
    )
    active_spec_store: str = "sqlite"                    # sqlite | postgres
    active_spec_lookup_strategy: str = "sap_then_local_store"

    # --- Layout model acquisition (Hugging Face) ---
    # HF repo id resolved via huggingface_hub by scripts/download_models.py.
    layout_model_hf_repo: str = "PaddlePaddle/PP-DocLayoutV3_safetensors"
    layout_device: str = "cpu"                           # cpu on MacBook, cuda on GPU box
    hf_cache_dir: Optional[Path] = None

    # --- OCR auth scheme (discrepancy #1: kept config-driven) ---
    ocr_auth_scheme: str = "bearer"                      # bearer | basic
    ocr_basic_user: str = ""
    ocr_basic_password: str = ""

    # --- IoU deduplication (Section 2A step 7) ---
    dedup_iou_threshold: float = 0.5
    dedup_containment_threshold: float = 0.8

    # Regions flagged for inspector review: empty text always; plus any region
    # whose OCR confidence is below this threshold (None disables the threshold).
    ocr_review_min_confidence: Optional[float] = None

    # --- Spec source root + indexing (2B). SPEC_NETWORK_ROOT points at a local
    # mock folder now; becomes a real UNC path later with no code change. ---
    spec_network_root: str = Field(
        default="data/spec_store/mock_specs",
        validation_alias=AliasChoices(
            "spec_network_root", "network_share_path", "spec_network_path",
            "spec_docs_unc_path", "spec_docs_folder",
        ),
    )
    spec_store_backend: str = "sqlite"
    spec_store_db_path: Path = Path("data/spec_store/spec_store.db")
    spec_output_dir: Path = Path("data/spec_store/outputs")
    spec_hash_algorithm: str = "sha256"
    spec_fuzzy_match_threshold: float = 0.85
    spec_reindex_if_hash_changed: bool = True
    spec_reindex_if_revision_changed: bool = True
    spec_index_mode: str = "incremental"                 # full | incremental
    spec_index_schedule: str = ""                        # cron expr (informational)
    # Force OCR for EVERY spec PDF (digital or scanned). When False, digital PDFs
    # with a usable text layer are read natively and only scanned ones fall back
    # to OCR. Default True per requirement: run all spec PDFs through OCR.
    spec_force_ocr: bool = True

    # --- Relational store (runs / findings / overrides; SQLite -> Postgres) ---
    database_url: str = "sqlite:///data/qc_inspector.db"
    db_echo: bool = False

    # --- Local OCR provider (PaddleOCR-VL in-process via transformers).
    # OPTIONAL: production topology keeps OCR remote; this is for local testing
    # on a machine with enough disk/RAM. Selected with
    # ACTIVE_OCR_PROVIDER=paddleocr_vl_local. Weights pulled by
    # scripts/download_models.py --ocr into ocr_local_model_dir. ---
    ocr_local_model_hf_repo: str = "PaddlePaddle/PaddleOCR-VL-1.6"
    ocr_local_model_dir: str = "models/PaddleOCR-VL-1.6"
    ocr_local_device: str = "cpu"
    ocr_local_dtype: str = "float32"
    ocr_local_max_new_tokens: int = 2048
    ocr_local_max_pixels: int = 1003520     # 1280*28*28 (model card OCR default)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def input_path(self) -> Path:
        return self.data_root / "input"

    @property
    def input_spec_path(self) -> Path:
        return self.input_path / "spec"

    @property
    def input_vendor_path(self) -> Path:
        return self.input_path / "vendor"

    @property
    def output_path(self) -> Path:
        return self.data_root / "output"

    @property
    def llm_tls_cert(self):
        # Sertifika yolları None veya boş değilse cert tuple döndür
        # Path('.') veya 'None' string'lerini filtrele
        if self.tls_client_cert_path and self.tls_client_key_path:
            cert_str = str(self.tls_client_cert_path)
            key_str = str(self.tls_client_key_path)
            # Path('.') veya 'None' string'lerini reddet
            if cert_str not in ('.', 'None') and key_str not in ('.', 'None'):
                return (cert_str, key_str)
        return None

    @property
    def tls_verify_option(self):
        if self.tls_ca_cert_path:
            return str(self.tls_ca_cert_path)
        return self.tls_verify

    @staticmethod
    def _verify_opt(ca_bundle, verify_flag, fallback):
        """httpx verify: CA-bundle path str if set, else the verify bool."""
        if ca_bundle:
            return str(ca_bundle)
        if verify_flag is False:
            return False
        return fallback

    @property
    def ocr_tls_verify(self):
        return self._verify_opt(self.ocr_remote_ca_bundle, self.ocr_remote_verify_tls, self.tls_verify_option)

    @property
    def llm_tls_verify(self):
        return self._verify_opt(self.llm_remote_ca_bundle, self.llm_remote_verify_tls, self.tls_verify_option)

    @property
    def sap_tls_verify(self):
        return self._verify_opt(self.sap_spec_service_ca_bundle, self.sap_spec_service_verify_tls, self.tls_verify_option)

    @property
    def output_dir(self) -> Path:
        """Vendor job artifacts root. OUTPUT_ROOT overrides <data_root>/output."""
        return Path(self.output_root) if self.output_root else self.output_path

    def validate_for_providers(self) -> list[str]:
        """Fail-fast: return a list of human-readable config problems for the
        selected providers (prompt Section 11). Empty list = OK."""
        problems: list[str] = []
        if self.active_ocr_provider == "paddleocr_vl" and not self.ocr_service_url:
            problems.append("OCR_PROVIDER=paddleocr_vl (remote) requires OCR_REMOTE_BASE_URL/OCR_SERVICE_URL")
        if self.active_llm_provider == "openai_compatible" and not self.llm_base_url:
            problems.append("LLM_PROVIDER=openai_compatible requires LLM_REMOTE_BASE_URL/LLM_SERVICE_URL")
        if self.active_sap_provider == "real" and not self.sap_spec_endpoint:
            problems.append("ACTIVE_SAP_PROVIDER=real requires SAP_SPEC_SERVICE_BASE_URL")
        if self.environment == "production":
            if self.active_ocr_provider == "paddleocr_vl" and not self.ocr_bearer_key:
                problems.append("production OCR requires OCR_REMOTE_BEARER_TOKEN")
            if not self.sap_spec_endpoint:
                problems.append("production requires SAP_SPEC_SERVICE_BASE_URL")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
