"""CLI: ingest every document in sample_docs/ into a fresh FAISS index.

Usage:
    python -m scripts.ingest_sample_docs
    python -m scripts.ingest_sample_docs --dry-run   # use fake embeddings, no API key needed
"""
from __future__ import annotations

import argparse
from pathlib import Path

from db import repository as db_repository
from db.session import init_db
from ingestion.chunker import get_chunker
from ingestion.loader import DocumentLoader
from ingestion.pipeline import guess_doc_type, ingest_document
from settings import BASE_DIR, get_settings
from vectorstore.embedder import FakeEmbeddingClient, get_embedding_client
from vectorstore.index import FaissVectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force fake (offline, deterministic) embeddings regardless of configured provider.",
    )
    args = parser.parse_args()

    settings = get_settings()
    sample_docs_dir = BASE_DIR / settings.paths.sample_docs_dir
    init_db(settings.database.url)

    embedder = FakeEmbeddingClient(dimensions=settings.embedding.dimensions) if args.dry_run else get_embedding_client(settings)
    loader = DocumentLoader()
    chunker = get_chunker(
        settings.chunking.strategy,
        max_chunk_chars=settings.chunking.max_chunk_chars,
        overlap_chars=settings.chunking.overlap_chars,
    )
    vectorstore = FaissVectorStore(dimensions=embedder.dimensions)

    doc_paths = sorted(
        p for p in sample_docs_dir.glob("*") if p.suffix.lower() in (".txt", ".pdf")
    )
    if not doc_paths:
        print(f"No .txt/.pdf documents found in {sample_docs_dir}")
        return

    total_chunks = 0
    for doc_path in doc_paths:
        doc_type = guess_doc_type(doc_path.name)
        result = ingest_document(str(doc_path), doc_type, loader, chunker, embedder, vectorstore)
        total_chunks += result.num_chunks
        db_repository.record_document(
            doc_id=result.metadata.doc_id,
            filename=doc_path.name,
            doc_type=doc_type.value,
            num_chunks=result.num_chunks,
            pii_chunks=result.pii_chunks_redacted,
        )
        print(
            f"ingested {doc_path.name} (doc_id={result.metadata.doc_id}, "
            f"doc_type={doc_type.value}, chunks={result.num_chunks}, "
            f"pii_redacted={result.pii_chunks_redacted})"
        )

    index_path = BASE_DIR / settings.vectorstore.index_path
    vectorstore.persist(str(index_path))
    print(f"\npersisted index with {total_chunks} total chunks to {index_path}")
    if args.dry_run:
        print("(dry-run: embeddings are fake/deterministic, not suitable for real retrieval quality)")


if __name__ == "__main__":
    main()
