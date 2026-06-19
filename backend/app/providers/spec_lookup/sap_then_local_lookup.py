"""Default spec lookup strategy: SAP -> local store -> fuzzy -> single-file
index -> clear error (Section 3).

`sap_spec_service` (text + spec_no from SAP) and the spec store / indexer are
distinct collaborators, orchestrated here rather than merged.
"""

from pathlib import Path

from app.core.logging import get_logger
from app.providers.spec_lookup.base import SpecLookupResult, SpecLookupStrategy
from app.services.spec_file_discovery_service import SpecFileDiscoveryService
from app.services.spec_indexing_service import SpecIndexingService
from app.services.spec_sources import get_spec_source
from app.utils.hash_utils import file_hash

logger = get_logger(__name__)


class SapThenLocalLookup(SpecLookupStrategy):
    name = "sap_then_local_store"

    def __init__(self, store=None, indexer: SpecIndexingService | None = None):
        from app.providers.factory import get_spec_store

        self._store = store or get_spec_store()
        self._indexer = indexer or SpecIndexingService(store=self._store)
        self._discovery = SpecFileDiscoveryService()

    def resolve(
        self,
        po_number=None,
        po_item=None,
        material=None,
        extra_specs=None,
    ) -> SpecLookupResult:
        # 1) SAP: spec_no candidate + spec_text fallback.
        sap = get_spec_source().fetch(po_number=po_number, po_item=po_item, material=material)
        candidates: list[str] = []
        if sap.spec_name:
            candidates.append(sap.spec_name)
        candidates.extend(extra_specs or [])
        candidates = [c for c in dict.fromkeys(candidates) if c]  # dedupe, keep order

        # 2-7) For each candidate: exact store -> fuzzy -> discover+index.
        for candidate in candidates:
            result = self._resolve_candidate(candidate)
            if result is not None:
                return result

        # SAP returned text but no file/store hit -> still usable for comparison.
        if sap.status == "success" and (sap.spec_text or "").strip():
            return SpecLookupResult(
                status="found",
                source="sap_text",
                spec_no=sap.spec_name,
                spec_text=sap.spec_text,
                message="SAP spec metni kullanildi (indeksli dosya bulunamadi)",
            )

        # Nothing anywhere -> structured error.
        stage = "sap_spec_fetch" if not candidates else "spec_lookup"
        return SpecLookupResult(
            status="not_found",
            stage=stage,
            spec_no=candidates[0] if candidates else None,
            message="Bu vendor dokumanina ait spec bulunamadi (SAP + yerel depo + network)",
        )

    def _resolve_candidate(self, candidate: str) -> SpecLookupResult | None:
        # 3) exact store match (reindex first if the file on disk changed).
        record = self._store.get_by_spec_no(candidate)
        if record:
            self._reindex_if_stale(record)
            record = self._store.get_by_spec_no(candidate) or record
            return self._from_record(record, source="local_store_exact")

        # 4) fuzzy match.
        matches = self._store.search(candidate, limit=1)
        if matches:
            return self._from_record(matches[0], source="fuzzy")

        # 5) found on the source root but not yet indexed -> index that one file.
        files = self._discovery.discover(name_filter=candidate)
        if files:
            self._indexer.index_file(files[0], force=False)
            record = self._store.get_by_file_path(files[0].file_path)
            if record:
                return self._from_record(record, source="freshly_indexed")
        return None

    def _reindex_if_stale(self, record: dict) -> None:
        # 8) stored hash differs from disk -> reindex that file before returning.
        path = record.get("file_path")
        if not path or not Path(path).exists():
            return
        try:
            if file_hash(Path(path)) != record.get("content_hash"):
                files = self._discovery.discover()
                for f in files:
                    if f.file_path == path:
                        logger.info("Spec hash degismis, yeniden indeksleniyor: %s", path)
                        self._indexer.index_file(f, force=True)
                        break
        except Exception as err:  # noqa: BLE001
            logger.warning("Hash kontrolu basarisiz (%s): %s", path, err)

    def _from_record(self, record: dict, source: str) -> SpecLookupResult:
        spec_id = record.get("id")
        sections = self._store.get_sections(spec_id) if spec_id else []
        references = self._store.get_references(spec_id) if spec_id else []
        return SpecLookupResult(
            status="found",
            source=source,
            spec_no=record.get("spec_no"),
            spec_text=record.get("text") or "",
            sections=sections,
            references=references,
            file_path=record.get("file_path"),
            message=f"Spec yerel depodan ({source})",
        )
