from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ingestion.chunker import BaseChunker
from ingestion.loader import DocumentLoader
from ingestion.metadata import Chunk, DocType, DocumentMetadata
from vectorstore.embedder import EmbeddingClient
from vectorstore.index import VectorStore


def _embedding_cache_key(text: str, model: str) -> str:
    return f"{model}::{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _embed_with_cache(embedder: EmbeddingClient, texts: list[str]) -> list[list[float]]:
    """Skips the embedding API call entirely for text that's already been
    embedded before (e.g. re-ingesting a document that changed only
    slightly, or the same boilerplate clause across many contracts). Falls
    back to uncached embedding if no database has been initialized (callers
    other than the API server aren't required to set one up)."""
    from db import repository as db_repository
    from db.session import get_engine

    try:
        get_engine()
    except RuntimeError:
        return embedder.embed_texts(texts)

    keys = [_embedding_cache_key(t, embedder.model) for t in texts]
    cached = [db_repository.get_cached_embedding(k) for k in keys]

    missing_indices = [i for i, v in enumerate(cached) if v is None]
    if missing_indices:
        fresh = embedder.embed_texts([texts[i] for i in missing_indices])
        for i, vector in zip(missing_indices, fresh):
            cached[i] = vector
            db_repository.put_cached_embedding(keys[i], vector)

    return cached


@dataclass
class IngestResult:
    metadata: DocumentMetadata
    num_chunks: int
    pii_chunks_redacted: int


_FILENAME_DOC_TYPE_HINTS: dict[str, DocType] = {
    "loan": DocType.LOAN_AGREEMENT,
    "invoice": DocType.INVOICE,
    "kyc": DocType.KYC_FORM,
    "financial_statement": DocType.FINANCIAL_STATEMENT,
}


def guess_doc_type(filename: str) -> DocType:
    lower = filename.lower()
    for hint, doc_type in _FILENAME_DOC_TYPE_HINTS.items():
        if hint in lower:
            return doc_type
    return DocType.OTHER


def ingest_document(
    path: str,
    doc_type: DocType,
    loader: DocumentLoader,
    chunker: BaseChunker,
    embedder: EmbeddingClient,
    vectorstore: VectorStore,
    tenant_id: str | None = None,
) -> IngestResult:
    """Ties loader -> chunker (which redacts PII) -> embedder -> vectorstore
    together. Shared by the FastAPI /ingest endpoint and the
    scripts/ingest_sample_docs.py CLI so the two never drift apart."""
    loaded_doc = loader.load(path, doc_type=doc_type)
    chunks: list[Chunk] = chunker.chunk_document(loaded_doc, doc_type)
    if tenant_id is not None:
        for chunk in chunks:
            chunk.tenant_id = tenant_id

    if chunks:
        embeddings = _embed_with_cache(embedder, [c.text for c in chunks])
        vectorstore.upsert(chunks, embeddings)

    pii_count = sum(1 for c in chunks if c.contains_pii)
    return IngestResult(
        metadata=loaded_doc.metadata,
        num_chunks=len(chunks),
        pii_chunks_redacted=pii_count,
    )
