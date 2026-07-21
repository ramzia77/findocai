import pytest

from db import repository as db_repository
from db.session import init_db


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db("sqlite:///:memory:")


def test_record_and_list_documents():
    db_repository.record_document(
        doc_id="d1", filename="a.pdf", doc_type="loan_agreement",
        num_chunks=3, pii_chunks=1, tenant_id="default",
    )
    docs = db_repository.list_documents()
    assert len(docs) == 1
    assert docs[0]["doc_id"] == "d1"
    assert docs[0]["num_chunks"] == 3


def test_record_document_upserts_by_doc_id():
    db_repository.record_document(doc_id="d1", filename="a.pdf", doc_type="other", num_chunks=1, pii_chunks=0)
    db_repository.record_document(doc_id="d1", filename="a.pdf", doc_type="other", num_chunks=5, pii_chunks=2)

    docs = db_repository.list_documents()
    assert len(docs) == 1
    assert docs[0]["num_chunks"] == 5
    assert docs[0]["pii_chunks"] == 2


def test_list_documents_filters_by_tenant():
    db_repository.record_document(doc_id="d1", filename="a.pdf", doc_type="other", num_chunks=1, pii_chunks=0, tenant_id="tenant-a")
    db_repository.record_document(doc_id="d2", filename="b.pdf", doc_type="other", num_chunks=1, pii_chunks=0, tenant_id="tenant-b")

    assert [d["doc_id"] for d in db_repository.list_documents(tenant_id="tenant-a")] == ["d1"]
    assert [d["doc_id"] for d in db_repository.list_documents(tenant_id="tenant-b")] == ["d2"]
    assert len(db_repository.list_documents()) == 2


def test_delete_document_returns_true_then_false():
    db_repository.record_document(doc_id="d1", filename="a.pdf", doc_type="other", num_chunks=1, pii_chunks=0)

    assert db_repository.delete_document("d1") is True
    assert db_repository.list_documents() == []
    assert db_repository.delete_document("d1") is False


def test_log_and_list_audit_most_recent_first():
    for i in range(3):
        db_repository.log_audit(
            request_id=f"r{i}", timestamp=f"2026-01-0{i + 1}T00:00:00Z", endpoint="/query",
            api_key_id="-key", tenant_id="default", doc_type=None, question=f"q{i}",
            retrieved_chunk_ids=[], answer="a", latency_ms=1.0, status_code=200,
        )

    records = db_repository.list_audit(limit=10)
    assert [r["request_id"] for r in records] == ["r2", "r1", "r0"]


def test_list_audit_respects_limit():
    for i in range(5):
        db_repository.log_audit(
            request_id=f"r{i}", timestamp=f"2026-01-0{i + 1}T00:00:00Z", endpoint="/query",
            api_key_id="-key", tenant_id="default", doc_type=None, question="q",
            retrieved_chunk_ids=[], answer="a", latency_ms=1.0, status_code=200,
        )

    assert len(db_repository.list_audit(limit=2)) == 2


def test_embedding_cache_roundtrip():
    assert db_repository.get_cached_embedding("missing") is None
    db_repository.put_cached_embedding("key1", [0.1, 0.2, 0.3])
    assert db_repository.get_cached_embedding("key1") == [0.1, 0.2, 0.3]

    db_repository.put_cached_embedding("key1", [0.9])  # overwrite
    assert db_repository.get_cached_embedding("key1") == [0.9]
