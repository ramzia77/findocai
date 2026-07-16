from ingestion.metadata import Chunk, DocType, SourceRef
from vectorstore.embedder import FakeEmbeddingClient
from vectorstore.index import FaissVectorStore


def _make_chunk(i: int) -> Chunk:
    source = SourceRef(
        doc_id="d1",
        filename="f.txt",
        page_number=1,
        section=None,
        chunk_id=f"d1::p1::c{i}",
        char_start=0,
        char_end=10,
    )
    return Chunk(text=f"chunk {i} text", raw_text=f"chunk {i} text", source=source, doc_type=DocType.OTHER)


def test_upsert_and_search_roundtrip():
    emb = FakeEmbeddingClient(dimensions=16)
    chunks = [_make_chunk(i) for i in range(5)]
    vecs = emb.embed_texts([c.text for c in chunks])

    store = FaissVectorStore(dimensions=16)
    store.upsert(chunks, vecs)

    query_vec = emb.embed_query(chunks[2].text)
    results = store.search(query_vec, top_k=1)

    assert len(results) == 1
    assert results[0].chunk.source.chunk_id == "d1::p1::c2"


def test_search_filters_by_doc_type():
    emb = FakeEmbeddingClient(dimensions=16)
    chunk_a = _make_chunk(0)
    source_b = SourceRef(
        doc_id="d2", filename="g.txt", page_number=1, section=None,
        chunk_id="d2::p1::c0", char_start=0, char_end=10,
    )
    chunk_b = Chunk(text="other doc text", raw_text="other doc text", source=source_b, doc_type=DocType.INVOICE)

    store = FaissVectorStore(dimensions=16)
    store.upsert([chunk_a, chunk_b], emb.embed_texts([chunk_a.text, chunk_b.text]))

    results = store.search(emb.embed_query(chunk_a.text), top_k=5, doc_type=DocType.INVOICE)
    assert all(r.chunk.doc_type == DocType.INVOICE for r in results)


def test_persist_and_load_roundtrip(tmp_path):
    emb = FakeEmbeddingClient(dimensions=16)
    chunks = [_make_chunk(i) for i in range(3)]
    vecs = emb.embed_texts([c.text for c in chunks])

    store = FaissVectorStore(dimensions=16)
    store.upsert(chunks, vecs)

    index_path = tmp_path / "test_index.faiss"
    store.persist(str(index_path))

    reloaded = FaissVectorStore(dimensions=16)
    reloaded.load(str(index_path))

    assert len(reloaded._chunks) == 3
    assert {c.source.chunk_id for c in reloaded._chunks} == {c.source.chunk_id for c in chunks}


def test_search_on_empty_store_returns_no_results():
    emb = FakeEmbeddingClient(dimensions=16)
    store = FaissVectorStore(dimensions=16)
    results = store.search(emb.embed_query("anything"), top_k=5)
    assert results == []
