"""Postgres spec store — drop-in swap point for SQLite (Section 2B).

Not implemented in this phase. The SpecStore interface and the SQLite schema are
intentionally portable; implement these methods against psycopg/SQLAlchemy when
moving to Postgres and select via ACTIVE_SPEC_STORE=postgres.
"""

from app.providers.spec_store.base import SpecStore


class PostgresSpecStore(SpecStore):
    name = "postgres"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "PostgresSpecStore is a future drop-in; set ACTIVE_SPEC_STORE=sqlite for now."
        )

    def get_by_spec_no(self, spec_no):  # pragma: no cover
        raise NotImplementedError

    def get_by_file_path(self, file_path):  # pragma: no cover
        raise NotImplementedError

    def upsert_spec(self, record):  # pragma: no cover
        raise NotImplementedError

    def replace_sections(self, spec_id, sections):  # pragma: no cover
        raise NotImplementedError

    def replace_references(self, spec_id, references):  # pragma: no cover
        raise NotImplementedError

    def get_sections(self, spec_id):  # pragma: no cover
        raise NotImplementedError

    def get_references(self, spec_id):  # pragma: no cover
        raise NotImplementedError

    def list_specs(self):  # pragma: no cover
        raise NotImplementedError

    def search(self, query, limit=10):  # pragma: no cover
        raise NotImplementedError

    def is_indexed(self, spec_no):  # pragma: no cover
        raise NotImplementedError
