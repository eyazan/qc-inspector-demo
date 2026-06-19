"""
Pipeline servisi — İKİ AŞAMALI akis.

Asama 1 (start_upload):  vendor OCR (ilk sayfa) -> PO/kalem/malzeme cikar
                         -> SAP'tan spec metni -> spec PDF bul + indeksle
                         -> awaiting_comparison (DUR). Onizleme verisi yazilir.
Asama 2 (start_comparison): vendor TUM sayfalar OCR -> segment -> compare
                         -> aggregate -> final rapor (completed).

Orijinal segmentation/comparison/aggregation/storage MANTIGI AYNEN korundu;
sadece tek `_run` ikiye bolundu ve run_id bazli state'e baglandi.
"""
import threading
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.factory import (
    get_layout_provider,
    get_ocr_provider,
    get_spec_lookup_strategy,
)
from app.services.aggregation_service import AggregationService
from app.services.comparison_service import ComparisonService
from app.services.metadata_extraction_service import MetadataExtractionService
from app.services.ocr import OcrPipeline
from app.services.ocr.models import DocumentSegment
from app.services.pipeline_state import get_run_state, drop_run_state
from app.services.segmentation_service import SegmentationService
from app.services.storage_service import StorageService

logger = get_logger(__name__)


class PipelineService:
    def __init__(self, storage: StorageService):
        self._storage = storage
        self._lock = threading.Lock()

    # ---------------- AŞAMA 1: YÜKLEME ----------------
    def start_upload(self, seed: dict | None = None) -> tuple[bool, str, str | None]:
        """Input klasorundeki vendor PDF'lerini al, run olustur, Asama 1'i baslat.

        seed: frontend'in start-full-pipeline govdesinden gelen opsiyonel
        po_number/po_item/material/inspector_id. Dolu alanlar OCR'dan cikarilan
        degerleri ezer; bos alanlar OCR/metadata cikarimina birakilir.
        """
        with self._lock:
            specs, vendors = self._storage.list_input_pdfs()
            if not vendors:
                return False, "Islenecek vendor PDF bulunamadi", None

            run_id = self._storage.create_run()
            state = get_run_state(run_id)
            state.begin(run_id)
            thread = threading.Thread(
                target=self._run_upload, args=(run_id, vendors, seed or {}), daemon=True
            )
            thread.start()
            return True, "Yukleme islemi baslatildi", run_id

    def _run_upload(self, run_id: str, vendors: list[Path], seed: dict | None = None) -> None:
        seed = seed or {}
        state = get_run_state(run_id)
        try:
            ocr_pipeline = OcrPipeline(get_layout_provider(), get_ocr_provider())

            # 1) Vendor PDF'i run'a kopyala + ilk sayfa(lar) OCR
            state.update("Vendor PDF OCR isleniyor (onizleme)", 30)
            vendor = vendors[0]
            self._storage.copy_pdf_into_run(run_id, vendor, is_spec=False)
            max_pages = settings.upload_ocr_max_pages or None
            regions = ocr_pipeline.run(vendor, max_pages=max_pages)
            self._storage.save_vendor_ocr_regions(
                run_id, vendor.stem, [r.to_dict() for r in regions]
            )

            # 2) Ilk sayfadan PO/kalem/malzeme + TUM spec referanslari (LLM + regex)
            state.update("Tesellum fisi okunuyor (PO/kalem/malzeme)", 55)
            first_page_text = self._first_page_text(regions)
            meta = MetadataExtractionService().extract(first_page_text, vendor.name)

            # Frontend'ten gelen degerler (seed) doluysa OCR cikarimini ezer.
            po_number = (seed.get("po_number") or "").strip() or (meta.po_number or "")
            po_item = (seed.get("po_item") or "").strip() or (meta.po_item or "")
            material = (seed.get("material") or "").strip() or (meta.material_number or "")

            preview = {
                "run_id": run_id,
                "vendor_filename": vendor.name,
                "vendor_doc_id": vendor.name,
                "po_number": po_number,
                "po_item": po_item,
                "material": material,
                "spec_references": meta.spec_references,
                "inspector_id": (seed.get("inspector_id") or "").strip(),
                "dedup_stats": ocr_pipeline.dedup_stats,
                "sap_spec_name": "",
                "sap_spec_text": "",
                "spec_doc_status": "",
            }
            self._storage.save_preview(run_id, preview)

            # 3+4) Spec cozumleme — Section 3 strateji zinciri
            # (SAP -> yerel depo exact -> fuzzy -> tek-dosya indeksleme -> hata).
            # SAP/spec hatasi pipeline'i COKERTMEZ; akis devam eder.
            state.update("Spec cozumleniyor (SAP + yerel depo)", 75)
            lookup = get_spec_lookup_strategy().resolve(
                po_number=po_number,
                po_item=po_item,
                material=material,
                extra_specs=meta.spec_references,
            )
            self._storage.update_preview(
                run_id,
                sap_spec_name=lookup.spec_no or "",
                sap_spec_text=lookup.spec_text or "",
                spec_doc_status=lookup.message,
                spec_lookup_source=lookup.source,
            )
            if lookup.status == "found" and lookup.file_path:
                src = Path(lookup.file_path)
                if src.exists():
                    self._storage.copy_spec_pdf_into_run(run_id, src)
            state.log(f"Spec durumu: {lookup.status} ({lookup.source or lookup.stage or '-'})")

            # 5) DUR — karsilastirma bekleniyor
            state.pause_for_comparison(run_id, "Yukleme tamamlandi")
        except Exception as error:  # noqa: BLE001
            logger.exception("Upload pipeline failed (run=%s)", run_id)
            state.fail(f"Yukleme hatasi: {error}")

    # ---------------- AŞAMA 2: KARŞILAŞTIRMA ----------------
    def start_comparison(self, run_id: str) -> tuple[bool, str]:
        with self._lock:
            state = get_run_state(run_id)
            if state.is_processing:
                return False, "Bu run zaten isleniyor"
            preview = self._storage.read_preview(run_id)
            if preview is None:
                return False, "Onizleme verisi yok (once yukleme yapin)"
            state.resume("Karsilastirma baslatildi")
            thread = threading.Thread(
                target=self._run_comparison, args=(run_id,), daemon=True
            )
            thread.start()
            return True, "Karsilastirma baslatildi"

    def _run_comparison(self, run_id: str) -> None:
        state = get_run_state(run_id)
        try:
            ocr_pipeline = OcrPipeline(get_layout_provider(), get_ocr_provider())
            segmentation = SegmentationService()
            comparison = ComparisonService()
            aggregation = AggregationService()

            # Spec metni: indekslenmis md veya SAP metni
            preview = self._storage.read_preview(run_id) or {}
            specification = self._load_specification(preview)
            if not specification.strip():
                state.log("UYARI: Spec metni yok, karsilastirma sinirli")

            # Vendor: TUM sayfalar (Asama 1 sadece ilk sayfayi OCR'lamis olabilir)
            state.update("Vendor tum sayfalar OCR isleniyor", 30)
            vendor_pdf = self._storage.vendor_pdf_file(run_id)
            regions = ocr_pipeline.run(vendor_pdf)  # tum sayfalar
            self._storage.save_vendor_ocr_regions(
                run_id, vendor_pdf.stem, [r.to_dict() for r in regions]
            )

            # Segmentasyon (orijinal mantik)
            state.update("Belgeler segmentlere ayriliyor", 60)
            segments = segmentation.segment(regions)
            state.log(f"{len(segments)} segment tespit edildi")

            # Karsilastirma (orijinal mantik)
            segment_reports = self._compare_segments(
                run_id, segments, specification, comparison, state
            )

            # Aggregation (orijinal mantik)
            state.update("Nihai rapor olusturuluyor", 95)
            final_report = aggregation.aggregate(segment_reports)
            self._storage.save_final_report(run_id, final_report)

            self._write_metadata(run_id, preview, segments)
            self._storage.clear_inputs()
            state.finish(run_id, "Islem tamamlandi", status="completed")
        except Exception as error:  # noqa: BLE001
            logger.exception("Comparison pipeline failed (run=%s)", run_id)
            state.fail(f"Karsilastirma hatasi: {error}")

    def _load_specification(self, preview: dict) -> str:
        # Asama 1'de spec lookup stratejisinin cozdugu spec metni preview'a
        # sap_spec_text olarak yazildi (yerel depo veya SAP metni).
        return preview.get("sap_spec_text") or ""

    def _compare_segments(self, run_id, segments, specification, comparison, state) -> list[dict]:
        state.update("Segmentler spec ile karsilastiriliyor", 80)
        reports = []
        total = max(len(segments), 1)
        for index, segment in enumerate(segments, start=1):
            report_text = comparison.compare(segment, specification)
            filename = self._storage.save_segment_report(run_id, index, report_text)
            reports.append(
                {
                    "doc_type": segment.doc_type,
                    "content": report_text,
                    "index": index,
                    "filename": filename,
                }
            )
            progress = 80 + int(15 * index / total)
            state.update(f"Segment {index}/{total} karsilastirildi", progress)
        return reports

    def _write_metadata(self, run_id, preview, segments) -> None:
        mount = self._storage._static_mount
        vendor_file = self._storage.vendor_pdf_file(run_id)
        spec_file = self._storage.spec_pdf_file(run_id)
        vendor_pdf_path = (
            f"{mount}/{run_id}/pdfs/vendor/{vendor_file.name}" if vendor_file else None
        )
        spec_pdf_path = (
            f"{mount}/{run_id}/pdfs/spec/{spec_file.name}" if spec_file else None
        )
        segment_meta = [
            {"index": i, "doc_type": s.doc_type, "filename": f"segment_{i}.md"}
            for i, s in enumerate(segments, start=1)
        ]
        metadata = {
            "run_id": run_id,
            "display_name": preview.get("po_number") or run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vendor_files": [vendor_file.name] if vendor_file else [],
            "spec_files": [spec_file.name] if spec_file else [],
            "spec_pdf_path": spec_pdf_path,
            "vendor_pdf_path": vendor_pdf_path,
            "po_number": preview.get("po_number"),
            "po_item": preview.get("po_item"),
            "material": preview.get("material"),
            "sap_spec_name": preview.get("sap_spec_name"),
            "segments": segment_meta,
            "final_report_filename": "final_report.md",
        }
        self._storage.write_metadata(run_id, metadata)

    # ---------------- yardimcilar ----------------
    def _first_page_text(self, regions) -> str:
        first = [r for r in regions if r.page_number == 1]
        ordered = sorted(first, key=lambda r: (r.bbox[1] if r.bbox else 0))
        return "\n".join(r.text for r in ordered if r.text)

    def status(self, run_id: str) -> dict:
        return get_run_state(run_id).snapshot()

    def cancel(self, run_id: str) -> None:
        get_run_state(run_id).request_cancel()
