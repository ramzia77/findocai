from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ingestion.metadata import DocType
from rag.chain import Citation


class QueryRequest(BaseModel):
    question: str
    doc_type: Optional[DocType] = None
    top_k: int = 5


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]


class ExtractRequest(BaseModel):
    doc_id: str
    doc_type: DocType


class ExtractResponse(BaseModel):
    doc_id: str
    doc_type: DocType
    fields: dict
    citations: list[Citation]


class IngestResponse(BaseModel):
    doc_id: str
    doc_type: DocType
    num_pages: int
    num_chunks: int
    pii_chunks_redacted: int


class HealthResponse(BaseModel):
    status: str
    vectorstore_backend: str
    llm_provider: str
    embedding_provider: str
