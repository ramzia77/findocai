from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class DocType(str, Enum):
    LOAN_AGREEMENT = "loan_agreement"
    INVOICE = "invoice"
    KYC_FORM = "kyc_form"
    FINANCIAL_STATEMENT = "financial_statement"
    OTHER = "other"


class DocumentMetadata(BaseModel):
    doc_id: str
    filename: str
    doc_type: DocType
    source_path: str
    num_pages: int
    ingested_at: str
    sha256: str


class SourceRef(BaseModel):
    """The citation unit. Flows unmodified from the chunker through the
    vectorstore, retriever, RAG chain, and API response."""

    doc_id: str
    filename: str
    page_number: int
    section: Optional[str] = None
    chunk_id: str
    char_start: int
    char_end: int


class Chunk(BaseModel):
    text: str  # redacted text -- the only text ever embedded or sent to an LLM
    raw_text: str  # original, unredacted text -- for authorized citation display only
    source: SourceRef
    doc_type: DocType
    contains_pii: bool = False
    # Access-control concern, deliberately not on SourceRef (the citation
    # identity contract) -- None means "no tenant scoping" (single-tenant
    # deployments, and back-compat with chunks persisted before this field
    # existed).
    tenant_id: Optional[str] = None
