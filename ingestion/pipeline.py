from __future__ import annotations

from dataclasses import dataclass

from ingestion.chunker import BaseChunker
from ingestion.loader import DocumentLoader
from ingestion.metadata import Chunk, DocType, DocumentMetadata
from vectorstore.embedder import EmbeddingClient
from vectorstore.index import VectorStore


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
) -> IngestResult:
    """Ties loader -> chunker (which redacts PII) -> embedder -> vectorstore
    together. Shared by the FastAPI /ingest endpoint and the
    scripts/ingest_sample_docs.py CLI so the two never drift apart."""
    loaded_doc = loader.load(path, doc_type=doc_type)
    chunks: list[Chunk] = chunker.chunk_document(loaded_doc, doc_type)

    if chunks:
        embeddings = embedder.embed_texts([c.text for c in chunks])
        vectorstore.upsert(chunks, embeddings)

    pii_count = sum(1 for c in chunks if c.contains_pii)
    return IngestResult(
        metadata=loaded_doc.metadata,
        num_chunks=len(chunks),
        pii_chunks_redacted=pii_count,
    )
