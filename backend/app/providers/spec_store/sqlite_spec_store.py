"""SQLite spec store (stdlib sqlite3, no ORM).

Normalized spec_no enables S-400 == S400 lookups; rapidfuzz provides fuzzy
ranking for near matches. Schema is intentionally small and self-contained so a
Postgres implementation can mirror it behind the same SpecStore interface.
"""

import re
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.spec_store.base import SpecStore

logger = get_logger(__name__)


def normalize_spec_no(spec_no: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (spec_no or "").upper())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_no TEXT NOT NULL,
    spec_no_norm TEXT NOT NULL,
    revision TEXT,
    file_name TEXT,
    file_path TEXT UNIQUE,
    content_hash TEXT,
    modified_time REAL,
    status TEXT DEFAULT 'pending',
    output_json_path TEXT,
    output_md_path TEXT,
    text TEXT,
    indexed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_specs_norm ON specs(spec_no_norm);
CREATE TABLE IF NOT EXISTS spec_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id INTEGER NOT NULL REFERENCES specs(id) ON DELETE CASCADE,
    section_no TEXT,
    title TEXT,
    page_number INTEGER,
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_sections_spec ON spec_sections(spec_id);
CREATE TABLE IF NOT EXISTS spec_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id INTEGER NOT NULL REFERENCES specs(id) ON DELETE CASCADE,
    referenced_spec_no TEXT,
    context TEXT,
    page_number INTEGER,
    indexed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_refs_spec ON spec_references(spec_id);
"""


class SqliteSpecStore(SpecStore):
    name = "sqlite"

    def __init__(self, db_path: Path | None = None):
        self._db_path = Path(db_path or settings.spec_store_db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ---------------- reads ----------------
    def get_by_spec_no(self, spec_no: str) -> Optional[dict]:
        norm = normalize_spec_no(spec_no)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM specs WHERE spec_no_norm = ? ORDER BY indexed_at DESC LIMIT 1",
                (norm,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_file_path(self, file_path: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM specs WHERE file_path = ?", (str(file_path),)
            ).fetchone()
        return dict(row) if row else None

    def get_sections(self, spec_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT section_no, title, page_number, text FROM spec_sections "
                "WHERE spec_id = ? ORDER BY id",
                (spec_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_references(self, spec_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT referenced_spec_no, context, page_number, indexed FROM spec_references "
                "WHERE spec_id = ? ORDER BY id",
                (spec_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_specs(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM specs ORDER BY spec_no_norm").fetchall()
        return [dict(r) for r in rows]

    def is_indexed(self, spec_no: str) -> bool:
        rec = self.get_by_spec_no(spec_no)
        return bool(rec and rec.get("status") == "indexed")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        norm = normalize_spec_no(query)
        specs = self.list_specs()
        scored = []
        threshold = settings.spec_fuzzy_match_threshold * 100
        for spec in specs:
            target = spec.get("spec_no_norm") or ""
            score = max(
                fuzz.ratio(norm, target),
                fuzz.partial_ratio(norm, target),
            )
            if norm and norm in target:
                score = 100.0
            if score >= threshold:
                scored.append((score, spec))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [{**spec, "match_score": round(score, 1)} for score, spec in scored[:limit]]

    # ---------------- writes ----------------
    def upsert_spec(self, record: dict) -> int:
        norm = normalize_spec_no(record.get("spec_no", ""))
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM specs WHERE file_path = ?",
                (record.get("file_path"),),
            ).fetchone()
            fields = {
                "spec_no": record.get("spec_no"),
                "spec_no_norm": norm,
                "revision": record.get("revision"),
                "file_name": record.get("file_name"),
                "file_path": record.get("file_path"),
                "content_hash": record.get("content_hash"),
                "modified_time": record.get("modified_time"),
                "status": record.get("status", "indexed"),
                "output_json_path": record.get("output_json_path"),
                "output_md_path": record.get("output_md_path"),
                "text": record.get("text"),
                "indexed_at": record.get("indexed_at"),
            }
            if existing:
                spec_id = existing["id"]
                cols = ", ".join(f"{k} = :{k}" for k in fields)
                conn.execute(f"UPDATE specs SET {cols} WHERE id = :id", {**fields, "id": spec_id})
            else:
                cols = ", ".join(fields)
                placeholders = ", ".join(f":{k}" for k in fields)
                cur = conn.execute(
                    f"INSERT INTO specs ({cols}) VALUES ({placeholders})", fields
                )
                spec_id = cur.lastrowid
        return spec_id

    def replace_sections(self, spec_id: int, sections: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM spec_sections WHERE spec_id = ?", (spec_id,))
            conn.executemany(
                "INSERT INTO spec_sections (spec_id, section_no, title, page_number, text) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        spec_id,
                        s.get("section_no"),
                        s.get("title"),
                        s.get("page_number"),
                        s.get("text"),
                    )
                    for s in sections
                ],
            )

    def replace_references(self, spec_id: int, references: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM spec_references WHERE spec_id = ?", (spec_id,))
            conn.executemany(
                "INSERT INTO spec_references (spec_id, referenced_spec_no, context, page_number, indexed) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        spec_id,
                        r.get("referenced_spec_no"),
                        r.get("context"),
                        r.get("page_number"),
                        1 if r.get("indexed") else 0,
                    )
                    for r in references
                ],
            )
