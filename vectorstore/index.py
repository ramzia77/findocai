from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import numpy as np
from pydantic import BaseModel

from ingestion.metadata import Chunk, DocType


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int, doc_type: DocType | None = None) -> list[ScoredChunk]: ...
    def delete(self, doc_id: str) -> None: ...
    def persist(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...


class FaissVectorStore:
    """faiss.IndexFlatIP over L2-normalized vectors (== cosine similarity),
    with a parallel JSONL sidecar of Chunk metadata, id-aligned with FAISS's
    internal ids. The sidecar stores full Chunk objects (including SourceRef),
    which is exactly the document shape a future AzureAISearchVectorStore or
    PineconeVectorStore would need -- no reshaping at migration time."""

    def __init__(self, dimensions: int):
        import faiss

        self.dimensions = dimensions
        self._index = faiss.IndexFlatIP(dimensions)
        self._chunks: list[Chunk] = []

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must be the same length")
        vectors = self._normalize(np.array(embeddings, dtype="float32"))
        self._index.add(vectors)
        self._chunks.extend(chunks)

    def search(self, query_embedding: list[float], top_k: int, doc_type: DocType | None = None) -> list[ScoredChunk]:
        if self._index.ntotal == 0:
            return []
        query = self._normalize(np.array([query_embedding], dtype="float32"))
        # Over-fetch when filtering by doc_type since FAISS itself is not filter-aware.
        fetch_k = top_k * 5 if doc_type is not None else top_k
        fetch_k = min(fetch_k, self._index.ntotal)
        scores, ids = self._index.search(query, fetch_k)

        results: list[ScoredChunk] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx == -1:
                continue
            chunk = self._chunks[idx]
            if doc_type is not None and chunk.doc_type != doc_type:
                continue
            results.append(ScoredChunk(chunk=chunk, score=float(score)))
            if len(results) >= top_k:
                break
        return results

    def delete(self, doc_id: str) -> None:
        # IndexFlatIP has no native delete-by-id support in this implementation;
        # callers needing to remove a document should re-ingest into a fresh
        # index built from the remaining source documents instead.
        raise NotImplementedError(
            "FaissVectorStore does not support in-place delete; rebuild the "
            "index via ingestion excluding the target doc_id."
        )

    def persist(self, path: str) -> None:
        import faiss

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(out_path))
        meta_path = out_path.with_suffix(out_path.suffix + ".meta.jsonl")
        with open(meta_path, "w", encoding="utf-8") as f:
            for chunk in self._chunks:
                f.write(chunk.model_dump_json() + "\n")

    def load(self, path: str) -> None:
        import faiss

        in_path = Path(path)
        self._index = faiss.read_index(str(in_path))
        meta_path = in_path.with_suffix(in_path.suffix + ".meta.jsonl")
        self._chunks = []
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._chunks.append(Chunk(**json.loads(line)))
