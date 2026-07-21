from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_db(database_url: str) -> Engine:
    """Idempotent: safe to call more than once (e.g. once per test's
    TestClient lifespan) -- re-creating tables against an already-migrated
    schema is a no-op. A fresh call always builds a fresh engine, so
    sqlite:///:memory: gives each caller (e.g. each test's TestClient
    context) a brand new, isolated, empty database."""
    global _engine, _SessionLocal

    engine_kwargs: dict = {}
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url in ("sqlite:///:memory:", "sqlite://"):
        # A plain :memory: sqlite connects a fresh, empty DB per connection
        # by default -- StaticPool pins the pool to a single connection so
        # every session in this process actually shares the same data.
        engine_kwargs["poolclass"] = StaticPool
    _engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    if database_url.startswith("sqlite"):
        # WAL mode is what actually gives us real concurrent-write safety --
        # the JSONL files this replaced had none (two simultaneous /ingest
        # calls could race on the same file).
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialized -- call init_db() first")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized -- call init_db() first")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
