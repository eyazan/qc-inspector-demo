"""Spec indexing pipeline (2B) — standalone, idempotent, runnable on demand.

NOT part of the vendor request path. Discovers spec PDFs, skips unchanged ones
(hash + revision), extracts text (native-first / OCR fallback), parses sections
and cross-references, writes them to the spec store plus a per-spec JSON+MD
artifact, and flags whether each referenced spec is itself indexed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.factory import get_spec_store
from app.services import spec_structure_parser as structure
from app.services.spec_file_discovery_service import SpecFile, SpecFileDiscoveryService
from app.services.spec_ocr_pipeline_service import SpecOcrPipelineService
from app.utils.hash_utils import file_hash

logger = get_logger(__name__)


def _build_ocr_pipeline():
    """Lazily build the shared layout+OCR pipeline for scanned spec fallback."""
    from app.providers.factory import get_layout_provider, get_ocr_provider
    from app.services.ocr import OcrPipeline

    return OcrPipeline(get_layout_provider(), get_ocr_provider())


class SpecIndexingService:
    def __init__(self, store=None, ocr_pipeline=None):
        self._store = store or get_spec_store()
        self._discovery = SpecFileDiscoveryService()
        self._ocr_pipeline = ocr_pipeline
        self._output_dir = Path(settings.spec_output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- public ----------------
    def run(self, mode: str = "incremental", spec_name: str | None = None) -> dict:
        files = self._discovery.discover(name_filter=spec_name)
        force = mode == "full"
        results = [self.index_file(f, force=force) for f in files]
        summary = {
            "mode": mode,
            "spec_name": spec_name,
            "discovered": len(files),
            "indexed": sum(1 for r in results if r["action"] in ("indexed", "reindexed")),
            "skipped": sum(1 for r in results if r["action"] == "skipped"),
            "failed": sum(1 for r in results if r["action"] == "failed"),
            "results": results,
        }
        logger.info(
            "Spec indexing %s: discovered=%s indexed=%s skipped=%s failed=%s",
            mode, summary["discovered"], summary["indexed"],
            summary["skipped"], summary["failed"],
        )
        return summary

    def index_file(self, spec_file: SpecFile, force: bool = False) -> dict:
        try:
            content_hash = file_hash(Path(spec_file.file_path))
            existing = self._store.get_by_file_path(spec_file.file_path)

            pages, source = self._extractor().extract_pages(Path(spec_file.file_path))
            full_text = "\n".join(pages)
            spec_no, revision = structure.extract_identity(full_text, spec_file.file_name)

            if existing and not force and not self._should_reindex(
                existing, content_hash, revision
            ):
                return {
                    "file": spec_file.file_name,
                    "spec_no": existing.get("spec_no"),
                    "action": "skipped",
                    "reason": "hash+revision unchanged",
                }

            sections = structure.parse_sections(pages)
            references = structure.detect_references(pages, spec_no)
            self._flag_indexed_references(references)

            record = {
                "spec_no": spec_no or Path(spec_file.file_name).stem,
                "revision": revision,
                "file_name": spec_file.file_name,
                "file_path": spec_file.file_path,
                "content_hash": content_hash,
                "modified_time": spec_file.modified_time,
                "status": "indexed",
                "text": full_text,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
            artifacts = self._write_artifacts(record, sections, references, source)
            record.update(artifacts)

            spec_id = self._store.upsert_spec(record)
            self._store.replace_sections(spec_id, sections)
            self._store.replace_references(spec_id, references)

            action = "reindexed" if existing else "indexed"
            return {
                "file": spec_file.file_name,
                "spec_no": record["spec_no"],
                "revision": revision,
                "action": action,
                "text_source": source,
                "sections": len(sections),
                "references": len(references),
            }
        except Exception as error:  # noqa: BLE001
            logger.exception("Spec indekslenemedi: %s", spec_file.file_name)
            return {"file": spec_file.file_name, "action": "failed", "error": str(error)}

    # ---------------- internals ----------------
    def _extractor(self) -> SpecOcrPipelineService:
        if self._ocr_pipeline is None:
            self._ocr_pipeline = _build_ocr_pipeline()
        return SpecOcrPipelineService(self._ocr_pipeline)

    def _should_reindex(self, existing: dict, content_hash: str, revision: str | None) -> bool:
        if settings.spec_reindex_if_hash_changed and existing.get("content_hash") != content_hash:
            return True
        if (
            settings.spec_reindex_if_revision_changed
            and (existing.get("revision") or None) != (revision or None)
        ):
            return True
        return False

    def _flag_indexed_references(self, references: list[dict]) -> None:
        for ref in references:
            ref["indexed"] = self._store.is_indexed(ref.get("referenced_spec_no", ""))

    def _write_artifacts(
        self, record: dict, sections: list[dict], references: list[dict], source: str
    ) -> dict:
        key = structure.normalize(record["spec_no"]) or "spec"
        json_path = self._output_dir / f"{key}.json"
        md_path = self._output_dir / f"{key}.md"

        payload = {
            "spec_no": record["spec_no"],
            "revision": record.get("revision"),
            "file_name": record["file_name"],
            "text_source": source,
            "sections": sections,
            "references": references,
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        md_lines = [f"# {record['spec_no']} (Rev {record.get('revision') or '-'})", ""]
        for sec in sections:
            md_lines.append(f"## {sec['section_no']} {sec['title']} (s.{sec['page_number']})")
            if sec["text"]:
                md_lines.append(sec["text"])
            md_lines.append("")
        if references:
            md_lines.append("## Referans verilen specler")
            for ref in references:
                flag = "indexli" if ref["indexed"] else "indeksli DEGIL"
                md_lines.append(
                    f"- {ref['referenced_spec_no']} (s.{ref['page_number']}, {flag})"
                )
        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        return {"output_json_path": str(json_path), "output_md_path": str(md_path)}
