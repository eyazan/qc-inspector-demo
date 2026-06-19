"""
ORM tablo modelleri.

Veri akisi:
    Run (1 vendor upload = 1 is emri)
     ├── Document* (vendor PDF'leri + eslesen spec)
     │    └── Region* (OCR cikti bolgeleri)
     ├── Segment* (belge turu gruplari)
     │    └── Finding* (compliance bulgulari)
     │         └── Override* (inspector mudahalesi)
     └── SpecRequirement* (spec'ten cikarilan yapisal gereksinimler)

Not: JSON tipi SQLite'ta TEXT, Postgres'te otomatik JSONB olur.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    """Bir vendor upload'inin tum yasam dongusu."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SAP / sorgu bilgileri
    po_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    po_item: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Durum: pending | processing | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    current_step: Mapped[str] = mapped_column(String(255), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    inspector_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Nihai birlesilmis rapor (markdown)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ASAMA 1'de SAP'tan alinan sartname metni (onizleme + Asama 2 girdisi)
    sap_spec_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_spec_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Spec dosya teyit durumu (onizlemede gosterilir)
    spec_doc_status: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["SpecRequirement"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Document(Base):
    """Run icindeki tek bir PDF (vendor veya spec)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)

    doc_kind: Mapped[str] = mapped_column(String(16))  # "vendor" | "spec"
    filename: Mapped[str] = mapped_column(String(255))
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # static mount yolu
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)  # tr|en|de|fr|mixed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped["Run"] = relationship(back_populates="documents")
    regions: Mapped[list["Region"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Region(Base):
    """Tek bir OCR bolgesi. 'hicbir seyi kacirma' icin needs_review bayragi tasir."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )

    region_id: Mapped[str] = mapped_column(String(64))  # "page3_region5"
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    region_type: Mapped[str] = mapped_column(String(32))  # table|formula|figure|text|...
    bbox: Mapped[list] = mapped_column(JSON)  # [x1, y1, x2, y2]

    text: Mapped[str] = mapped_column(Text, default="")
    # Tablo -> satir/sutun yapisi, formul -> latex, figure -> olculer vb.
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Dusuk guven / OCR hatasi / bos cikti -> inspector gozden gecirmeli
    needs_review: Mapped[bool] = mapped_column(default=False, index=True)
    crop_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # region kirpilmis gorsel

    document: Mapped["Document"] = relationship(back_populates="regions")


class Segment(Base):
    """Belge turu grubu (orn. mill_certificate sayfalari)."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)

    seq: Mapped[int] = mapped_column(Integer)  # run icindeki sira
    doc_type: Mapped[str] = mapped_column(String(64))  # mill_certificate, ...
    page_range: Mapped[list] = mapped_column(JSON)  # [3, 7]
    seg_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    region_ids: Mapped[list] = mapped_column(JSON, default=list)

    # Segment bazli ham karsilastirma raporu (markdown)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="segments")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )


class SpecRequirement(Base):
    """
    Spec'ten bir kez cikarilan yapisal gereksinim.
    RAG yerine bu kompakt, kayipsiz liste kullanilir.
    """

    __tablename__ = "spec_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)

    section_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # "3.5.1"
    parameter: Mapped[str] = mapped_column(String(255))  # "Tensile Strength"
    limit_type: Mapped[str] = mapped_column(String(16))  # min|max|range|exact|nominal
    value_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_exact: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)  # MPa|HB|%|...
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # ham spec ifadesi
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)  # chemical|mechanical|dimensional

    run: Mapped["Run"] = relationship(back_populates="requirements")


class Finding(Base):
    """Yapisal compliance bulgusu — bir requirement'in vendor karsiligi."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("spec_requirements.id", ondelete="SET NULL"), nullable=True
    )

    parameter: Mapped[str] = mapped_column(String(255))
    spec_value: Mapped[str | None] = mapped_column(String(255), nullable=True)  # gosterim icin
    vendor_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # COMPLIANT | NON_COMPLIANT | PARTIAL | MISSING | NOT_COVERED
    status: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")  # HIGH|MEDIUM|LOW
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec_section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Deterministik katman mi LLM mi uretti
    source: Mapped[str] = mapped_column(String(16), default="deterministic")  # deterministic|llm

    segment: Mapped["Segment"] = relationship(back_populates="findings")
    overrides: Mapped[list["Override"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class Override(Base):
    """Inspector mudahalesi — AI sonucunu onayla/reddet/duzelt."""

    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )

    inspector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(16))  # approve|reject|edit
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    finding: Mapped["Finding"] = relationship(back_populates="overrides")


class SpecIndex(Base):
    """
    Network-path spec PDF indeksleme tablosu.

    Akis: spec_no ile network path'te *spec_no* aranir, bulunan PDF (tek ise
    direkt, coklu ise date_modified en yeni) bu tabloda kontrol edilir.
    Ayni dosya (file_name + date_modified) zaten islenmisse tekrar OCR edilmez;
    mevcut md_path / ocr_text kullanilir.
    """

    __tablename__ = "spec_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    spec_no: Mapped[str] = mapped_column(String(128), index=True)
    file_name: Mapped[str] = mapped_column(String(512), index=True)
    file_path: Mapped[str] = mapped_column(Text)  # tam UNC yolu
    # Dosyanin son degistirilme zamani (epoch saniye) — degisirse yeniden islenir
    date_modified: Mapped[float] = mapped_column(Float, index=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # OCR ciktilari
    md_path: Mapped[str | None] = mapped_column(Text, nullable=True)   # .md dosya yolu
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # tam spec metni (cache)

    # Durum: processed | failed | pending
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
