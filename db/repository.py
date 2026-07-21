from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from db.models import AuditRecordRow, DocumentRecord, EmbeddingCacheEntry
from db.session import session_scope


def record_document(
    *,
    doc_id: str,
    filename: str,
    doc_type: str,
    num_chunks: int,
    pii_chunks: int,
    tenant_id: str = "default",
) -> None:
    with session_scope() as session:
        existing = session.get(DocumentRecord, doc_id)
        if existing is not None:
            existing.filename = filename
            existing.doc_type = doc_type
            existing.num_chunks = num_chunks
            existing.pii_chunks = pii_chunks
            existing.tenant_id = tenant_id
        else:
            session.add(
                DocumentRecord(
                    doc_id=doc_id,
                    filename=filename,
                    doc_type=doc_type,
                    num_chunks=num_chunks,
                    pii_chunks=pii_chunks,
                    tenant_id=tenant_id,
                    created_at=datetime.now(timezone.utc),
                )
            )


def list_documents(tenant_id: Optional[str] = None) -> list[dict]:
    with session_scope() as session:
        query = session.query(DocumentRecord)
        if tenant_id is not None:
            query = query.filter(DocumentRecord.tenant_id == tenant_id)
        rows = query.order_by(DocumentRecord.created_at.desc()).all()
        return [
            {
                "doc_id": r.doc_id,
                "filename": r.filename,
                "doc_type": r.doc_type,
                "num_chunks": r.num_chunks,
                "pii_chunks": r.pii_chunks,
            }
            for r in rows
        ]


def delete_document(doc_id: str) -> bool:
    with session_scope() as session:
        row = session.get(DocumentRecord, doc_id)
        if row is None:
            return False
        session.delete(row)
        return True


def log_audit(
    *,
    request_id: str,
    timestamp: str,
    endpoint: str,
    api_key_id: str,
    tenant_id: str,
    doc_type: Optional[str],
    question: str,
    retrieved_chunk_ids: list[str],
    answer: str,
    latency_ms: float,
    status_code: int,
) -> None:
    with session_scope() as session:
        session.add(
            AuditRecordRow(
                request_id=request_id,
                timestamp=timestamp,
                endpoint=endpoint,
                api_key_id=api_key_id,
                tenant_id=tenant_id,
                doc_type=doc_type,
                question=question,
                retrieved_chunk_ids=retrieved_chunk_ids,
                answer=answer,
                latency_ms=latency_ms,
                status_code=status_code,
            )
        )


def list_audit(limit: int = 50, tenant_id: Optional[str] = None) -> list[dict]:
    with session_scope() as session:
        query = session.query(AuditRecordRow)
        if tenant_id is not None:
            query = query.filter(AuditRecordRow.tenant_id == tenant_id)
        rows = query.order_by(AuditRecordRow.timestamp.desc()).limit(limit).all()
        return [
            {
                "request_id": r.request_id,
                "timestamp": r.timestamp,
                "endpoint": r.endpoint,
                "api_key_id": r.api_key_id,
                "doc_type": r.doc_type,
                "question": r.question,
                "retrieved_chunk_ids": r.retrieved_chunk_ids,
                "answer": r.answer,
                "latency_ms": r.latency_ms,
                "status_code": r.status_code,
            }
            for r in rows
        ]


def get_cached_embedding(cache_key: str) -> Optional[list[float]]:
    with session_scope() as session:
        row = session.get(EmbeddingCacheEntry, cache_key)
        return row.vector if row is not None else None


def put_cached_embedding(cache_key: str, vector: list[float]) -> None:
    with session_scope() as session:
        existing = session.get(EmbeddingCacheEntry, cache_key)
        if existing is not None:
            existing.vector = vector
        else:
            session.add(EmbeddingCacheEntry(cache_key=cache_key, vector=vector))
