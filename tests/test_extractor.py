import pytest
from pydantic import ValidationError

from ingestion.metadata import Chunk, DocType, SourceRef
from rag.chain import FakeLLMClient
from rag.extractor import StructuredExtractor
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever


def _seeded_retriever() -> Retriever:
    source = SourceRef(
        doc_id="d1", filename="loan.txt", page_number=1, section=None,
        chunk_id="d1::p1::c0", char_start=0, char_end=10,
    )
    chunk = Chunk(text="Loan terms", raw_text="Loan terms", source=source, doc_type=DocType.LOAN_AGREEMENT)
    emb = FakeEmbeddingClient(dimensions=16)
    store = FaissVectorStore(dimensions=16)
    store.upsert([chunk], emb.embed_texts([chunk.text]))
    return Retriever(store, emb)


def test_extract_validates_and_returns_citations():
    retriever = _seeded_retriever()
    llm = FakeLLMClient(
        canned_tool_args={"borrower": "Acme LLC", "lender": "First Bank", "principal_amount": 100000.0}
    )
    extractor = StructuredExtractor(retriever, llm)

    result = extractor.extract("d1", DocType.LOAN_AGREEMENT)

    assert result.fields["borrower"] == "Acme LLC"
    assert result.fields["principal_amount"] == 100000.0
    assert len(result.citations) == 1
    assert result.citations[0].source.chunk_id == "d1::p1::c0"


def test_extract_raises_on_missing_document():
    emb = FakeEmbeddingClient(dimensions=16)
    store = FaissVectorStore(dimensions=16)
    retriever = Retriever(store, emb)
    extractor = StructuredExtractor(retriever, FakeLLMClient(canned_tool_args={}))

    with pytest.raises(ValueError):
        extractor.extract("nonexistent-doc", DocType.LOAN_AGREEMENT)


def test_extract_raises_on_schema_validation_failure():
    retriever = _seeded_retriever()
    # Missing required fields (lender, principal_amount).
    llm = FakeLLMClient(canned_tool_args={"borrower": "Acme LLC"})
    extractor = StructuredExtractor(retriever, llm)

    with pytest.raises(ValidationError):
        extractor.extract("d1", DocType.LOAN_AGREEMENT)


def test_extract_rejects_unregistered_doc_type():
    retriever = _seeded_retriever()
    extractor = StructuredExtractor(retriever, FakeLLMClient(canned_tool_args={}))

    with pytest.raises(ValueError):
        extractor.extract("d1", DocType.FINANCIAL_STATEMENT)
