from fastapi.testclient import TestClient

from api.main import app
from ingestion.metadata import Chunk, DocType, SourceRef
from rag.chain import FakeLLMClient, RAGChain
from rag.extractor import StructuredExtractor
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever

VALID_API_KEY = "dev-local-key"  # matches config.yaml's default api.keys entry


def _seed_known_state(client_app):
    """Injects a retriever/chain wired to a known fixture chunk so API tests
    don't depend on whatever index happens to be persisted on disk."""
    source = SourceRef(
        doc_id="d1", filename="loan.txt", page_number=1, section="Sec A",
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
    retriever = Retriever(store, emb, top_k=3)

    client_app.state.rag_chain = RAGChain(retriever, FakeLLMClient(canned_answer="6.75% [1]"))
    client_app.state.extractor = StructuredExtractor(
        retriever, FakeLLMClient(canned_tool_args={"borrower": "Acme LLC", "lender": "First Bank", "principal_amount": 100000.0})
    )


def test_health_returns_ok():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_query_without_api_key_is_unauthorized():
    with TestClient(app) as client:
        r = client.post("/query", json={"question": "test"})
        assert r.status_code == 401


def test_query_with_invalid_api_key_is_unauthorized():
    with TestClient(app) as client:
        r = client.post("/query", json={"question": "test"}, headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401


def test_query_with_valid_key_returns_answer_and_citations():
    with TestClient(app) as client:
        _seed_known_state(app)
        r = client.post(
            "/query",
            json={"question": "What is the interest rate?"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == "6.75% [1]"
        assert body["citations"][0]["source"]["chunk_id"] == "d1::p1::c0"


def test_extract_with_valid_key_returns_validated_fields():
    with TestClient(app) as client:
        _seed_known_state(app)
        r = client.post(
            "/extract",
            json={"doc_id": "d1", "doc_type": "loan_agreement"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["fields"]["borrower"] == "Acme LLC"
        assert body["fields"]["principal_amount"] == 100000.0


def test_extract_unknown_doc_returns_422():
    with TestClient(app) as client:
        _seed_known_state(app)
        r = client.post(
            "/extract",
            json={"doc_id": "nonexistent", "doc_type": "loan_agreement"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert r.status_code == 422
