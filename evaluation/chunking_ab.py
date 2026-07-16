"""Compare chunking strategies by retrieval hit-rate against evaluation/test_set.json.

Runs entirely offline using FakeEmbeddingClient (deterministic hash-based
vectors), so hit-rate numbers here are illustrative of the plumbing, not of
real retrieval quality -- re-run with a configured OPENAI_API_KEY /
Azure OpenAI credentials for a meaningful comparison.

Usage:
    python -m evaluation.chunking_ab
"""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.chunker import ChunkingStrategy, get_chunker
from ingestion.loader import DocumentLoader
from ingestion.pipeline import guess_doc_type
from settings import BASE_DIR, get_settings
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever

TEST_SET_PATH = Path(__file__).resolve().parent / "test_set.json"
FAKE_EMBEDDING_DIMENSIONS = 64


def load_test_set(path: Path = TEST_SET_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_index_for_strategy(strategy: ChunkingStrategy, doc_paths: list[Path]) -> Retriever:
    embedder = FakeEmbeddingClient(dimensions=FAKE_EMBEDDING_DIMENSIONS)
    loader = DocumentLoader()
    chunker = get_chunker(strategy)
    vectorstore = FaissVectorStore(dimensions=FAKE_EMBEDDING_DIMENSIONS)

    for path in doc_paths:
        doc_type = guess_doc_type(path.name)
        loaded_doc = loader.load(str(path), doc_type=doc_type)
        chunks = chunker.chunk_document(loaded_doc, doc_type)
        if chunks:
            embeddings = embedder.embed_texts([c.text for c in chunks])
            vectorstore.upsert(chunks, embeddings)

    return Retriever(vectorstore, embedder, top_k=5)


def retrieval_hit_rate(retriever: Retriever, test_set: list[dict], top_k: int = 5) -> dict:
    """For each question, checks whether any ground-truth chunk id appears in
    the top_k retrieved results, and at what rank."""
    reciprocal_ranks: list[float] = []
    hits = 0

    for item in test_set:
        results = retriever.retrieve(item["question"], top_k=top_k)
        ground_truth_ids = set(item["ground_truth_chunk_ids"])
        rank = next(
            (i for i, sc in enumerate(results, start=1) if sc.chunk.source.chunk_id in ground_truth_ids),
            None,
        )
        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(test_set)
    return {
        "hit_rate": hits / n if n else 0.0,
        "mean_reciprocal_rank": sum(reciprocal_ranks) / n if n else 0.0,
        "num_questions": n,
    }


def compare_strategies(strategies: list[ChunkingStrategy], doc_paths: list[Path], test_set: list[dict]):
    import pandas as pd

    rows = []
    for strategy in strategies:
        retriever = build_index_for_strategy(strategy, doc_paths)
        metrics = retrieval_hit_rate(retriever, test_set)
        rows.append(
            {
                "strategy": strategy.value,
                "total_chunks": len(retriever.vectorstore._chunks),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    settings = get_settings()
    sample_docs_dir = BASE_DIR / settings.paths.sample_docs_dir
    doc_paths = sorted(p for p in sample_docs_dir.glob("*") if p.suffix.lower() in (".txt", ".pdf"))
    test_set = load_test_set()

    df = compare_strategies([ChunkingStrategy.SECTION_AWARE, ChunkingStrategy.FIXED_SIZE], doc_paths, test_set)
    print(df.to_string(index=False))
    print(
        "\n(NOTE: retrieval uses FakeEmbeddingClient -- hit-rate numbers are illustrative "
        "of the pipeline only, not of real retrieval quality.)"
    )


if __name__ == "__main__":
    main()
