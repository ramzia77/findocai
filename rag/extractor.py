from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ingestion.metadata import DocType
from rag.chain import Citation, LLMClient
from vectorstore.index import ScoredChunk
from vectorstore.retriever import Retriever

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class LoanAgreementFields(BaseModel):
    borrower: str
    lender: str
    principal_amount: float
    currency: str = "USD"
    interest_rate: Optional[float] = None
    origination_date: Optional[str] = None
    maturity_date: Optional[str] = None
    governing_law: Optional[str] = None
    covenants: list[str] = []


class InvoiceFields(BaseModel):
    invoice_number: str
    vendor_name: str
    customer_name: str
    invoice_date: str
    due_date: Optional[str] = None
    currency: str = "USD"
    line_items: list[InvoiceLineItem] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: float


class KYCFields(BaseModel):
    full_name: str
    date_of_birth: Optional[str] = None
    id_type: Optional[str] = None
    id_number_last4: Optional[str] = None  # never the full ID number
    address: Optional[str] = None
    nationality: Optional[str] = None


DOC_TYPE_SCHEMAS: dict[DocType, type[BaseModel]] = {
    DocType.LOAN_AGREEMENT: LoanAgreementFields,
    DocType.INVOICE: InvoiceFields,
    DocType.KYC_FORM: KYCFields,
}


class ExtractionResult(BaseModel):
    doc_id: str
    doc_type: DocType
    fields: dict
    citations: list[Citation]
    raw_tool_arguments: dict


class StructuredExtractor:
    def __init__(self, retriever: Retriever, llm_client: LLMClient):
        self.retriever = retriever
        self.llm_client = llm_client
        self._system_prompt = (PROMPTS_DIR / "extraction_system.txt").read_text(encoding="utf-8")

    def extract(self, doc_id: str, doc_type: DocType, tenant_id: str | None = None) -> ExtractionResult:
        if doc_type not in DOC_TYPE_SCHEMAS:
            raise ValueError(f"No extraction schema registered for doc_type={doc_type!r}")
        schema_model = DOC_TYPE_SCHEMAS[doc_type]

        chunks = self._gather_context(doc_id, tenant_id=tenant_id)
        tool = self._pydantic_to_tool_schema(schema_model, doc_type)

        from rag.chain import ChatMessage

        context_block = "\n\n".join(f"({sc.chunk.source.chunk_id})\n{sc.chunk.text}" for sc in chunks)
        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=f"Document context:\n{context_block}"),
        ]

        tool_choice = {"type": "function", "function": {"name": tool["function"]["name"]}}
        result = self.llm_client.chat_with_tools(messages, tools=[tool], tool_choice=tool_choice)

        # Re-validate the model's output against the schema -- a validation
        # failure surfaces as a clear error rather than silently returning
        # malformed JSON.
        validated = schema_model(**result.arguments)

        citations = [Citation(source=sc.chunk.source, snippet=sc.chunk.text) for sc in chunks]
        return ExtractionResult(
            doc_id=doc_id,
            doc_type=doc_type,
            fields=validated.model_dump(),
            citations=citations,
            raw_tool_arguments=result.arguments,
        )

    def _gather_context(self, doc_id: str, tenant_id: str | None = None) -> list[ScoredChunk]:
        # Extraction needs the whole document, not a similarity-ranked subset,
        # so pull every chunk belonging to doc_id directly from the store.
        vectorstore = self.retriever.vectorstore
        all_chunks = getattr(vectorstore, "_chunks", None)
        if all_chunks is None:
            raise RuntimeError("Vectorstore backend does not expose stored chunks for extraction")
        matching = [
            c
            for c in all_chunks
            if c.source.doc_id == doc_id
            # A chunk with no tenant_id predates multi-tenancy / single-tenant
            # deployment -- visible to any tenant, same rule as FAISS search.
            and (tenant_id is None or c.tenant_id is None or c.tenant_id == tenant_id)
        ]
        if not matching:
            raise ValueError(f"No ingested chunks found for doc_id={doc_id!r}")
        return [ScoredChunk(chunk=c, score=1.0) for c in matching]

    def _pydantic_to_tool_schema(self, model: type[BaseModel], doc_type: DocType) -> dict:
        return {
            "type": "function",
            "function": {
                "name": f"extract_{doc_type.value}",
                "description": f"Extract structured fields for a {doc_type.value} document.",
                "parameters": model.model_json_schema(),
            },
        }
