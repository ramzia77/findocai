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


class DocumentSummary(BaseModel):
    """One row per ingested document, aggregated from its chunks -- backs
    the /documents endpoint and the web UI's Documents page."""

    doc_id: str
    filename: str
    doc_type: DocType
    num_chunks: int
    pii_chunks: int


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def search(
        self,
        query_embedding: list[float],
        top_k: int,
        doc_type: DocType | None = None,
        tenant_id: str | None = None,
    ) -> list[ScoredChunk]: ...
    def delete(self, doc_id: str) -> None: ...
    def list_documents(self) -> list[DocumentSummary]: ...
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

    def search(
        self,
        query_embedding: list[float],
        top_k: int,
        doc_type: DocType | None = None,
        tenant_id: str | None = None,
    ) -> list[ScoredChunk]:
        if self._index.ntotal == 0:
            return []
        query = self._normalize(np.array([query_embedding], dtype="float32"))
        # Over-fetch when filtering (doc_type and/or tenant_id) since FAISS
        # itself isn't filter-aware -- this is a brute-force post-filter,
        # fine at this scale; a managed vector DB migration would push the
        # filter down into the index itself.
        filtering = doc_type is not None or tenant_id is not None
        fetch_k = top_k * 5 if filtering else top_k
        fetch_k = min(fetch_k, self._index.ntotal)
        scores, ids = self._index.search(query, fetch_k)

        results: list[ScoredChunk] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx == -1:
                continue
            chunk = self._chunks[idx]
            if doc_type is not None and chunk.doc_type != doc_type:
                continue
            # A chunk with no tenant_id (None) predates multi-tenancy or was
            # ingested in a single-tenant deployment -- treat it as visible
            # to every tenant rather than invisible to all of them.
            if tenant_id is not None and chunk.tenant_id is not None and chunk.tenant_id != tenant_id:
                continue
            results.append(ScoredChunk(chunk=chunk, score=float(score)))
            if len(results) >= top_k:
                break
        return results

    def delete(self, doc_id: str) -> None:
        keep_indices = [i for i, c in enumerate(self._chunks) if c.source.doc_id != doc_id]
        if len(keep_indices) == len(self._chunks):
            return  # doc_id not present -- nothing to do

        import faiss

        new_index = faiss.IndexFlatIP(self.dimensions)
        if keep_indices:
            # IndexFlatIP stores raw vectors contiguously, so reconstructing
            # and re-adding the surviving ones needs no re-embedding -- the
            # embedding API is never called for a delete.
            all_vectors = self._index.reconstruct_n(0, self._index.ntotal)
            new_index.add(all_vectors[keep_indices])
        self._index = new_index
        self._chunks = [self._chunks[i] for i in keep_indices]

    def list_documents(self) -> list[DocumentSummary]:
        summaries: dict[str, DocumentSummary] = {}
        for chunk in self._chunks:
            summary = summaries.get(chunk.source.doc_id)
            if summary is None:
                summary = DocumentSummary(
                    doc_id=chunk.source.doc_id,
                    filename=chunk.source.filename,
                    doc_type=chunk.doc_type,
                    num_chunks=0,
                    pii_chunks=0,
                )
                summaries[chunk.source.doc_id] = summary
            summary.num_chunks += 1
            if chunk.contains_pii:
                summary.pii_chunks += 1
        return list(summaries.values())

    def persist(self, path: str) -> None:
        import faiss

        from encryption import encrypt_text

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(out_path))
        meta_path = out_path.with_suffix(out_path.suffix + ".meta.jsonl")
        with open(meta_path, "w", encoding="utf-8") as f:
            for chunk in self._chunks:
                # raw_text is the original, unredacted source text -- the
                # single most sensitive field on disk here. `text` (already
                # PII-redacted, and what's actually embedded/searched) is
                # left as-is. encrypt_text is a no-op without
                # FINDOCAI_ENCRYPTION_KEY set.
                record = chunk.model_dump()
                record["raw_text"] = encrypt_text(record["raw_text"])
                f.write(json.dumps(record) + "\n")

    def load(self, path: str) -> None:
        import faiss

        from encryption import decrypt_text

        in_path = Path(path)
        loaded_index = faiss.read_index(str(in_path))
        if loaded_index.d != self.dimensions:
            # Otherwise this fails much later and far less clearly: the
            # index loads "successfully" here, and the first upsert() then
            # crashes with a bare AssertionError deep inside faiss, with no
            # indication that the real cause was a stale index left over
            # from a different embedding model/provider.
            raise ValueError(
                f"Index at {path} has dimension {loaded_index.d}, but this "
                f"store was created for dimension {self.dimensions} -- it was "
                "likely persisted by a different embedding model/provider. "
                "Delete the stale index and re-ingest, or point config.yaml "
                "at a fresh vectorstore.index_path."
            )
        self._index = loaded_index
        meta_path = in_path.with_suffix(in_path.suffix + ".meta.jsonl")
        self._chunks = []
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    record["raw_text"] = decrypt_text(record["raw_text"])
                    self._chunks.append(Chunk(**record))
