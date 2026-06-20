from functools import lru_cache
from pathlib import Path
from typing import Annotated, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
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

    data_root: Path = Path("data")
    static_mount_path: str = "/files"

    layout_service_url: str = "http://localhost:8101"
    layout_detect_path: str = "/layout/detect"
    layout_timeout_seconds: int = 1800
    # --- DocLayout LOKAL (PP-DocLayoutV3, paddlex) ---
    layout_model_name: str = "PP-DocLayoutV3"
    layout_model_dir: str = "models/PP-DocLayoutV3_safetensors"
    layout_score_threshold: float = 0.10  # dusuk esik -> daha cok bolge

    ocr_service_url: str = "http://localhost:8102"
    ocr_recognize_path: str = "/ocr/recognize"
    ocr_timeout_seconds: int = 1800
    ocr_max_concurrency: int = 4
    ocr_bearer_key: str = ""
    ocr_model_name: str = "paddleocr-vl-16"

    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "qwen3"
    llm_api_key: str = "not-needed"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 8192
    llm_no_think_suffix: str = ""
    segmentation_timeout_seconds: int = 600
    comparison_timeout_seconds: int = 600
    aggregation_timeout_seconds: int = 300

    pdf_render_dpi: int = 150
    borderline_threshold_ratio: float = 0.10

    spec_source_dir: Path = Path("data/specs")

    # --- Spec kaynagi (SAP / local) ---
    spec_source: str = "local"  # "sap" | "local"
    # SAP endpoint: .env'de SAP_SPEC_ENDPOINT veya PO_API_BASE_URL (gercek servis adi)
    sap_spec_endpoint: str = Field(
        default="", validation_alias=AliasChoices("sap_spec_endpoint", "po_api_base_url")
    )
    sap_spec_read_path: str = "/read-text"
    sap_spec_timeout_seconds: int = Field(
        default=150, validation_alias=AliasChoices("sap_spec_timeout_seconds", "po_api_timeout")
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
    spec_ocr_max_pages: int = 1             # spec OCR ilk N sayfa (0 -> tum)

    # --- Iki asamali akis: yukleme (Asama 1) ilk N sayfa OCR ---
    upload_ocr_max_pages: int = 1           # 0 -> tum sayfalar

    tls_ca_cert_path: Optional[Path] = None
    tls_client_cert_path: Optional[Path] = None
    tls_client_key_path: Optional[Path] = None
    tls_verify: bool = True

    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Provider selection (Section 6) — swap a model/provider via .env only.
    # ------------------------------------------------------------------
    active_layout_provider: str = "paddlex_doclayout"   # local on every machine
    active_ocr_provider: str = "paddleocr_vl"           # paddleocr_vl (remote) | paddleocr_vl_local
    active_llm_provider: str = "openai_compatible"      # any OpenAI-compatible endpoint
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
            "spec_network_root", "spec_docs_unc_path", "spec_docs_folder"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
