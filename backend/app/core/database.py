"""
Veritabani baglanti katmani.

Tasarim hedefi: SQLite ile basla, tek config degisikligiyle PostgreSQL'e gec.
- SQLite:   sqlite:///data/qc_inspector.db
- Postgres: postgresql+psycopg://user:pass@host:5432/qc_inspector

SQLAlchemy soyutlamasi sayesinde servis/repository kodu DB tipinden bagimsizdir.
JSON alanlari SQLite'ta TEXT, Postgres'te JSONB olarak otomatik map'lenir.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Tum ORM modellerinin ortak tabani."""
    pass


def _build_engine():
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")

    connect_args = {}
    if is_sqlite:
        # SQLite + FastAPI thread havuzu icin gerekli
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        echo=settings.db_echo,
        future=True,
        connect_args=connect_args,
        # Postgres'te connection pool; SQLite'ta etkisiz ama zararsiz
        pool_pre_ping=not is_sqlite,
    )

    if is_sqlite:
        # SQLite'ta WAL modu: es zamanli okuma + tek yazar.
        # Orta olcek (5-20 inspector) icin yeterli; agir yukte Postgres'e gecilir.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    logger.info("Database engine kuruldu: %s", "sqlite" if is_sqlite else "postgres")
    return engine


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """
    Tablolari olustur. Production'da Alembic migration kullanilir;
    bu fonksiyon gelistirme/ilk kurulum kolayligi icindir.
    """
    # models import edilmeli ki Base.metadata tablolari tanisin
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tablolari hazir")


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Transaction-safe session context manager.

    Kullanim:
        with session_scope() as db:
            db.add(obj)
        # otomatik commit / hata durumunda rollback
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency injection icin session saglayici."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
