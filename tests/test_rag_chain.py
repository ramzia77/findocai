from ingestion.metadata import Chunk, DocType, SourceRef
from rag.chain import FakeLLMClient, RAGChain
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever


def _build_retriever() -> Retriever:
    source = SourceRef(
        doc_id="d1", filename="f.txt", page_number=1, section="Sec A",
        chunk_id="d1::p1::c0", char_start=0, char_end=10,
    )
    chunk = Chunk(
        text="The interest rate is 6.75%.",
        raw_text="The interest rate is 6.75%.",
        source=source,
        doc_type=DocType.LOAN_AGREEMENT,
    )
    emb = FakeEmbeddingClient(dimensions=16)
    store = FaissVectorStore(dimensions=16)
    store.upsert([chunk], emb.embed_texts([chunk.text]))
    return Retriever(store, emb, top_k=3)


def test_rag_chain_returns_answer_and_citations():
    retriever = _build_retriever()
    llm = FakeLLMClient(canned_answer="6.75% [1]")
    chain = RAGChain(retriever, llm)

    result = chain.answer("What is the interest rate?")

    assert result.answer == "6.75% [1]"
    assert len(result.citations) == 1
    assert result.citations[0].source.chunk_id == "d1::p1::c0"


def test_rag_chain_redacts_pii_in_question_before_prompting():
    retriever = _build_retriever()
    llm = FakeLLMClient(canned_answer="ok")
    chain = RAGChain(retriever, llm)

    chain.answer("My SSN is 523-11-8890, what is the rate?")

    user_message = llm.last_messages[-1].content
    assert "523-11-8890" not in user_message
    assert "[REDACTED:SSN]" in user_message


def test_rag_chain_numbers_context_matching_citation_order():
    retriever = _build_retriever()
    llm = FakeLLMClient(canned_answer="ok")
    chain = RAGChain(retriever, llm)

    result = chain.answer("What is the interest rate?")

    user_message = llm.last_messages[-1].content
    assert "[1]" in user_message
    assert result.citations[0].source.chunk_id == "d1::p1::c0"
