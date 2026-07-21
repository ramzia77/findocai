from fastapi.testclient import TestClient

from api.main import app
from db import repository as db_repository
from ingestion.metadata import Chunk, DocType, SourceRef
from rag.chain import FakeLLMClient, RAGChain
from rag.extractor import StructuredExtractor
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever

VALID_API_KEY = "dev-local-key"  # matches config.yaml's default api.keys entry


def _seed_known_state(client_app):
    """Injects a retriever/chain wired to a known fixture chunk (FAISS +
    document registry) so API tests don't depend on whatever index/DB state
    happens to exist -- each test gets a fresh in-memory DB via conftest.py's
    DATABASE_URL override, so this also re-seeds the document registry."""
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
    client_app.state.vectorstore = store
    db_repository.record_document(
        doc_id="d1", filename="loan.txt", doc_type=DocType.LOAN_AGREEMENT.value,
        num_chunks=1, pii_chunks=0,
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


def test_documents_without_api_key_is_unauthorized():
    with TestClient(app) as client:
        r = client.get("/documents")
        assert r.status_code == 401


def test_documents_lists_ingested_docs():
    with TestClient(app) as client:
        _seed_known_state(app)
        r = client.get("/documents", headers={"X-API-Key": VALID_API_KEY})
        assert r.status_code == 200
        docs = r.json()["documents"]
        assert len(docs) == 1
        assert docs[0]["doc_id"] == "d1"
        assert docs[0]["filename"] == "loan.txt"
        assert docs[0]["num_chunks"] == 1
        assert docs[0]["pii_chunks"] == 0


def test_audit_without_api_key_is_unauthorized():
    with TestClient(app) as client:
        r = client.get("/audit")
        assert r.status_code == 401


def test_audit_returns_recent_records():
    with TestClient(app) as client:
        db_repository.log_audit(
            request_id="r1",
            timestamp="2026-01-01T00:00:00Z",
            endpoint="/query",
            api_key_id="-key",
            tenant_id="default",
            doc_type=None,
            question="What is the interest rate?",
            retrieved_chunk_ids=["d1::p1::c0"],
            answer="6.75%",
            latency_ms=12.5,
            status_code=200,
        )

        r = client.get("/audit", headers={"X-API-Key": VALID_API_KEY})

        assert r.status_code == 200
        records = r.json()["records"]
        assert len(records) == 1
        assert records[0]["request_id"] == "r1"
        assert records[0]["question"] == "What is the interest rate?"


def test_audit_with_no_records_returns_empty_list():
    with TestClient(app) as client:
        r = client.get("/audit", headers={"X-API-Key": VALID_API_KEY})

        assert r.status_code == 200
        assert r.json()["records"] == []


def _with_scoped_key(scopes: list[str]):
    """Temporarily adds a 'scoped-test-key' with only the given scopes to
    app.state.settings (the same Settings singleton require_scope() reads
    from), so tests can exercise 403s without touching config.yaml."""
    from settings import ApiKeyEntry

    original_keys = list(app.state.settings.api.keys)
    app.state.settings.api.keys = original_keys + [
        ApiKeyEntry(key="scoped-test-key", scopes=scopes, tenant_id="default")
    ]
    return original_keys


def test_delete_document_requires_admin_scope():
    with TestClient(app) as client:
        _seed_known_state(app)
        original_keys = _with_scoped_key(["query", "read"])  # no 'admin'
        try:
            r = client.delete("/documents/d1", headers={"X-API-Key": "scoped-test-key"})
        finally:
            app.state.settings.api.keys = original_keys
        assert r.status_code == 403


def test_delete_document_removes_it_and_then_404s():
    with TestClient(app) as client:
        _seed_known_state(app)

        r = client.delete("/documents/d1", headers={"X-API-Key": VALID_API_KEY})
        assert r.status_code == 204

        r = client.get("/documents", headers={"X-API-Key": VALID_API_KEY})
        assert r.json()["documents"] == []

        r = client.delete("/documents/d1", headers={"X-API-Key": VALID_API_KEY})
        assert r.status_code == 404


def test_ingest_rejects_file_over_size_limit():
    with TestClient(app) as client:
        original_max = app.state.settings.upload.max_bytes
        app.state.settings.upload.max_bytes = 10  # bytes -- trivially small
        try:
            r = client.post(
                "/ingest",
                data={"doc_type": "other"},
                files={"file": ("big.txt", b"x" * 1000, "text/plain")},
                headers={"X-API-Key": VALID_API_KEY},
            )
        finally:
            app.state.settings.upload.max_bytes = original_max
        assert r.status_code == 413


def test_ingest_rejects_content_mismatched_extension():
    with TestClient(app) as client:
        r = client.post(
            "/ingest",
            data={"doc_type": "other"},
            # .pdf extension but no %PDF- magic bytes -- should be rejected
            # before it ever reaches the loader/OCR pipeline.
            files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert r.status_code == 400


def test_ready_reports_ok_checks_when_healthy():
    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["vectorstore"] == "ok"


def test_ready_does_not_require_api_key():
    # Readiness must be checkable by an orchestrator/load balancer that
    # doesn't have (and shouldn't need) an API key.
    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code in (200, 503)
