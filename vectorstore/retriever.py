from __future__ import annotations

from ingestion.metadata import DocType
from vectorstore.embedder import EmbeddingClient
from vectorstore.index import ScoredChunk, VectorStore


class Retriever:
    def __init__(self, vectorstore: VectorStore, embedding_client: EmbeddingClient, top_k: int = 5):
        self.vectorstore = vectorstore
        self.embedding_client = embedding_client
        self.top_k = top_k

    def retrieve(
        self, query: str, doc_type: DocType | None = None, top_k: int | None = None
    ) -> list[ScoredChunk]:
        query_embedding = self.embedding_client.embed_query(query)
        return self.vectorstore.search(query_embedding, top_k=top_k or self.top_k, doc_type=doc_type)
