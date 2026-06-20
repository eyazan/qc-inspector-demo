from pathlib import Path

from app.providers.spec_store.sqlite_spec_store import SqliteSpecStore
from app.services.spec_indexing_service import SpecIndexingService
from app.utils.hash_utils import file_hash, text_hash


def test_file_hash_changes_with_content(tmp_path: Path):
    f = tmp_path / "spec.txt"
    f.write_text("AMS4911 Rev T")
    h1 = file_hash(f)
    f.write_text("AMS4911 Rev U")
    h2 = file_hash(f)
    assert h1 != h2


def test_text_hash_stable():
    assert text_hash("same") == text_hash("same")
    assert text_hash("a") != text_hash("b")


def _indexer(tmp_path: Path) -> SpecIndexingService:
    store = SqliteSpecStore(db_path=tmp_path / "store.db")
    return SpecIndexingService(store=store)


def test_should_reindex_on_hash_change(tmp_path: Path):
    idx = _indexer(tmp_path)
    existing = {"content_hash": "aaa", "revision": "T"}
    assert idx._should_reindex(existing, content_hash="bbb", revision="T") is True


def test_should_not_reindex_when_unchanged(tmp_path: Path):
    idx = _indexer(tmp_path)
    existing = {"content_hash": "aaa", "revision": "T"}
    assert idx._should_reindex(existing, content_hash="aaa", revision="T") is False


def test_should_reindex_on_revision_change(tmp_path: Path):
    idx = _indexer(tmp_path)
    existing = {"content_hash": "aaa", "revision": "T"}
    assert idx._should_reindex(existing, content_hash="aaa", revision="U") is True
