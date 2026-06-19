"""Spec store repository interface.

SQLite to start; Postgres is a drop-in swap behind this interface (Section 2B).
A "spec" record carries identity (spec_no, revision), provenance (file_path,
content_hash, modified_time) and indexing status. Sections and cross-references
are child rows.
"""

from abc import ABC, abstractmethod
from typing import Optional


class SpecStore(ABC):
    name: str = "base"

    @abstractmethod
    def get_by_spec_no(self, spec_no: str) -> Optional[dict]:
        """Exact match on normalized spec_no (S-400 == S400). None if absent."""

    @abstractmethod
    def get_by_file_path(self, file_path: str) -> Optional[dict]:
        ...

    @abstractmethod
    def upsert_spec(self, record: dict) -> int:
        """Insert/update a spec; returns spec_id."""

    @abstractmethod
    def replace_sections(self, spec_id: int, sections: list[dict]) -> None:
        ...

    @abstractmethod
    def replace_references(self, spec_id: int, references: list[dict]) -> None:
        ...

    @abstractmethod
    def get_sections(self, spec_id: int) -> list[dict]:
        ...

    @abstractmethod
    def get_references(self, spec_id: int) -> list[dict]:
        ...

    @abstractmethod
    def list_specs(self) -> list[dict]:
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Normalized exact + fuzzy match on spec_no/file_name."""

    @abstractmethod
    def is_indexed(self, spec_no: str) -> bool:
        ...
