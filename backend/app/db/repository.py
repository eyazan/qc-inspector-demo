"""
Repository katmani — tum DB erisimini tek yerde toplar.

Servisler dogrudan ORM sorgusu yazmaz; bu katmani cagirir.
Boylece DB semasi degisirse tek nokta guncellenir, ve ileride
Postgres'e gecis sirasinda sorgu optimizasyonu burada yapilir.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_logger
from app.db import models

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- Run ----
    def create_run(
        self,
        run_id: str,
        po_number: str | None = None,
        po_item: str | None = None,
        material: str | None = None,
        inspector_id: str | None = None,
    ) -> models.Run:
        run = models.Run(
            id=run_id,
            display_name=run_id,
            po_number=po_number,
            po_item=po_item,
            material=material,
            inspector_id=inspector_id,
            status="pending",
            created_at=_utcnow(),
        )
        self.db.add(run)
        self.db.flush()
        return run

    def get_run(self, run_id: str) -> models.Run | None:
        return self.db.get(models.Run, run_id)

    def update_run_status(
        self, run_id: str, status: str, step: str = "", progress: int | None = None
    ) -> None:
        run = self.db.get(models.Run, run_id)
        if run is None:
            return
        run.status = status
        if step:
            run.current_step = step
        if progress is not None:
            run.progress = progress
        if status == "processing" and run.started_at is None:
            run.started_at = _utcnow()
        if status in {"completed", "failed", "cancelled"}:
            run.finished_at = _utcnow()
        self.db.flush()

    def set_run_error(self, run_id: str, message: str) -> None:
        run = self.db.get(models.Run, run_id)
        if run:
            run.status = "failed"
            run.error_message = message
            run.finished_at = _utcnow()
            self.db.flush()

    def save_final_report(self, run_id: str, markdown: str) -> None:
        run = self.db.get(models.Run, run_id)
        if run:
            run.final_report = markdown
            self.db.flush()

    def update_run_po(self, run_id: str, po_number, po_item, material) -> None:
        """Asama 1'de tesellum fisinden cikarilan kimlik bilgilerini yaz."""
        run = self.db.get(models.Run, run_id)
        if run:
            run.po_number = po_number
            run.po_item = po_item
            run.material = material
            self.db.flush()

    def save_sap_spec(self, run_id: str, spec_text: str, spec_name) -> None:
        """SAP'tan alinan sartname metnini sakla (onizleme + Asama 2 girdisi)."""
        run = self.db.get(models.Run, run_id)
        if run:
            run.sap_spec_text = spec_text
            run.sap_spec_name = spec_name
            self.db.flush()

    def save_spec_doc_status(self, run_id: str, status: str) -> None:
        run = self.db.get(models.Run, run_id)
        if run:
            run.spec_doc_status = status
            self.db.flush()

    def get_preview(self, run_id: str) -> dict | None:
        """Asama 1 sonrasi onizleme verisi (vendor+spec yan yana)."""
        run = self.db.get(models.Run, run_id)
        if run is None:
            return None
        # vendor ve spec belge bilgileri
        vendor_doc = self.db.scalars(
            select(models.Document)
            .where(models.Document.run_id == run_id)
            .where(models.Document.doc_kind == "vendor")
        ).first()
        spec_doc = self.db.scalars(
            select(models.Document)
            .where(models.Document.run_id == run_id)
            .where(models.Document.doc_kind == "spec")
        ).first()
        return {
            "run_id": run.id,
            "status": run.status,
            "po_number": run.po_number,
            "po_item": run.po_item,
            "material": run.material,
            "sap_spec_name": run.sap_spec_name,
            "sap_spec_text": run.sap_spec_text or "",
            "spec_doc_status": run.spec_doc_status or "",
            "vendor_filename": vendor_doc.filename if vendor_doc else None,
            "vendor_doc_id": vendor_doc.id if vendor_doc else None,
            "spec_filename": spec_doc.filename if spec_doc else None,
        }

    def replace_vendor_regions(self, run_id: str, filename: str, regions: list) -> None:
        """Asama 2 tam OCR: verilen vendor dosyasinin region'larini silip yenisini yaz."""
        doc = self.db.scalars(
            select(models.Document)
            .where(models.Document.run_id == run_id)
            .where(models.Document.doc_kind == "vendor")
            .where(models.Document.filename == filename)
        ).first()
        if doc is None:
            return
        # Eski region'lari sil
        for old in self.db.scalars(
            select(models.Region).where(models.Region.document_id == doc.id)
        ):
            self.db.delete(old)
        self.db.flush()
        # Yeni region'lari ekle (OcrRegion -> dict)
        region_dicts = []
        for r in regions:
            region_dicts.append({
                "region_id": getattr(r, "region_id", ""),
                "text": getattr(r, "text", "") or "",
                "bbox": getattr(r, "bbox", None) or [],
                "page_number": getattr(r, "page_number", 1),
                "region_type": getattr(r, "region_type", "text"),
                "confidence": getattr(r, "confidence", None),
                "structured_data": getattr(r, "structured_data", None),
                "needs_review": getattr(r, "needs_review", False),
                "crop_path": getattr(r, "crop_path", None),
            })
        self.add_regions(doc.id, region_dicts)
        self.db.flush()

    def get_vendor_regions(self, run_id: str) -> list[dict]:
        """Asama 2 icin: run'a ait vendor belgelerinin region'larini dict olarak getir."""
        docs = self.db.scalars(
            select(models.Document)
            .where(models.Document.run_id == run_id)
            .where(models.Document.doc_kind == "vendor")
        )
        result: list[dict] = []
        for doc in docs:
            regions = self.db.scalars(
                select(models.Region).where(models.Region.document_id == doc.id)
            )
            for r in regions:
                result.append({
                    "region_id": r.region_id,
                    "text": r.text or "",
                    "bbox": r.bbox or [],
                    "page_number": r.page_number,
                    "region_type": r.region_type,
                    "confidence": r.confidence,
                    "structured_data": r.structured_data,
                    "needs_review": r.needs_review,
                    "crop_path": r.crop_path,
                })
        return result

    def list_runs(self, limit: int = 100, inspector_id: str | None = None) -> list[models.Run]:
        stmt = select(models.Run).order_by(models.Run.created_at.desc()).limit(limit)
        if inspector_id:
            stmt = stmt.where(models.Run.inspector_id == inspector_id)
        return list(self.db.scalars(stmt))

    def rename_run(self, run_id: str, new_name: str) -> bool:
        run = self.db.get(models.Run, run_id)
        if run is None:
            return False
        run.display_name = new_name
        self.db.flush()
        return True

    def delete_run(self, run_id: str) -> bool:
        run = self.db.get(models.Run, run_id)
        if run is None:
            return False
        self.db.delete(run)  # cascade tum bagli kayitlari siler
        self.db.flush()
        return True

    # ---- Document ----
    def add_document(
        self,
        run_id: str,
        doc_kind: str,
        filename: str,
        pdf_path: str | None = None,
        page_count: int = 0,
        language: str | None = None,
    ) -> models.Document:
        doc = models.Document(
            run_id=run_id,
            doc_kind=doc_kind,
            filename=filename,
            pdf_path=pdf_path,
            page_count=page_count,
            language=language,
        )
        self.db.add(doc)
        self.db.flush()
        return doc

    # ---- Region ----
    def add_regions(self, document_id: int, regions: list[dict]) -> None:
        objs = [
            models.Region(
                document_id=document_id,
                region_id=r["region_id"],
                page_number=r["page_number"],
                region_type=r["region_type"],
                bbox=r["bbox"],
                text=r.get("text", ""),
                structured_data=r.get("structured_data"),
                confidence=r.get("confidence"),
                needs_review=r.get("needs_review", False),
                crop_path=r.get("crop_path"),
            )
            for r in regions
        ]
        self.db.add_all(objs)
        self.db.flush()

    def regions_needing_review(self, run_id: str) -> list[models.Region]:
        stmt = (
            select(models.Region)
            .join(models.Document)
            .where(models.Document.run_id == run_id)
            .where(models.Region.needs_review.is_(True))
        )
        return list(self.db.scalars(stmt))

    # ---- Segment ----
    def add_segment(
        self,
        run_id: str,
        seq: int,
        doc_type: str,
        page_range: list,
        metadata: dict,
        region_ids: list,
    ) -> models.Segment:
        seg = models.Segment(
            run_id=run_id,
            seq=seq,
            doc_type=doc_type,
            page_range=page_range,
            seg_metadata=metadata,
            region_ids=region_ids,
        )
        self.db.add(seg)
        self.db.flush()
        return seg

    def save_segment_report(self, segment_id: int, markdown: str) -> None:
        seg = self.db.get(models.Segment, segment_id)
        if seg:
            seg.report_markdown = markdown
            self.db.flush()

    def get_segments(self, run_id: str) -> list[models.Segment]:
        stmt = (
            select(models.Segment)
            .where(models.Segment.run_id == run_id)
            .order_by(models.Segment.seq)
            .options(selectinload(models.Segment.findings))
        )
        return list(self.db.scalars(stmt))

    # ---- SpecRequirement ----
    def add_requirements(self, run_id: str, requirements: list[dict]) -> list[models.SpecRequirement]:
        objs = [
            models.SpecRequirement(
                run_id=run_id,
                section_ref=req.get("section_ref"),
                parameter=req["parameter"],
                limit_type=req.get("limit_type", "exact"),
                value_min=req.get("value_min"),
                value_max=req.get("value_max"),
                value_exact=req.get("value_exact"),
                unit=req.get("unit"),
                raw_text=req.get("raw_text"),
                category=req.get("category"),
            )
            for req in requirements
        ]
        self.db.add_all(objs)
        self.db.flush()
        return objs

    def get_requirements(self, run_id: str) -> list[models.SpecRequirement]:
        stmt = select(models.SpecRequirement).where(models.SpecRequirement.run_id == run_id)
        return list(self.db.scalars(stmt))

    # ---- Finding ----
    def add_findings(self, segment_id: int, findings: list[dict]) -> None:
        objs = [
            models.Finding(
                segment_id=segment_id,
                requirement_id=f.get("requirement_id"),
                parameter=f["parameter"],
                spec_value=f.get("spec_value"),
                vendor_value=f.get("vendor_value"),
                unit=f.get("unit"),
                status=f["status"],
                severity=f.get("severity", "MEDIUM"),
                rationale=f.get("rationale"),
                spec_section=f.get("spec_section"),
                page_ref=f.get("page_ref"),
                deviation_pct=f.get("deviation_pct"),
                source=f.get("source", "deterministic"),
            )
            for f in findings
        ]
        self.db.add_all(objs)
        self.db.flush()

    def get_findings(self, run_id: str, status: str | None = None) -> list[models.Finding]:
        stmt = (
            select(models.Finding)
            .join(models.Segment)
            .where(models.Segment.run_id == run_id)
            .options(selectinload(models.Finding.overrides))
        )
        if status:
            stmt = stmt.where(models.Finding.status == status)
        return list(self.db.scalars(stmt))

    # ---- Override ----
    def add_override(
        self,
        finding_id: int,
        action: str,
        inspector_id: str | None = None,
        new_status: str | None = None,
        new_value: str | None = None,
        note: str | None = None,
    ) -> models.Override:
        ov = models.Override(
            finding_id=finding_id,
            action=action,
            inspector_id=inspector_id,
            new_status=new_status,
            new_value=new_value,
            note=note,
        )
        self.db.add(ov)
        # Finding'in efektif durumunu guncelle (son override gecerli)
        finding = self.db.get(models.Finding, finding_id)
        if finding and new_status:
            finding.status = new_status
        self.db.flush()
        return ov
