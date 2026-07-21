from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    """The document registry -- system of record for /documents. Replaces
    scanning FAISS's in-memory chunk list on every request."""

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String)
    num_chunks: Mapped[int] = mapped_column(Integer)
    pii_chunks: Mapped[int] = mapped_column(Integer)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuditRecordRow(Base):
    """The compliance audit trail -- system of record for /audit. `question`
    and `answer` may hold Fernet-encrypted ciphertext (base64 text) once
    encryption at rest is enabled; this table doesn't know or care, that's
    the caller's concern (see api/auth.py)."""

    __tablename__ = "audit_records"

    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String, index=True)
    endpoint: Mapped[str] = mapped_column(String)
    api_key_id: Mapped[str] = mapped_column(String)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    question: Mapped[str] = mapped_column(Text)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int] = mapped_column(Integer)


class EmbeddingCacheEntry(Base):
    """sha256(chunk text)+model -> embedding vector, so re-ingesting
    unchanged content skips the embedding API call entirely."""

    __tablename__ = "embedding_cache"

    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    vector: Mapped[list] = mapped_column(JSON)
