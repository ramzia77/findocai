from ingestion.chunker import ChunkingStrategy, FixedSizeChunker, SectionAwareChunker, get_chunker
from ingestion.loader import DocumentLoader
from ingestion.metadata import DocType


def test_section_aware_detects_headings(sample_docs_dir):
    loader = DocumentLoader()
    doc = loader.load(str(sample_docs_dir / "sample_loan_agreement.txt"), doc_type=DocType.LOAN_AGREEMENT)
    chunker = SectionAwareChunker()
    chunks = chunker.chunk_document(doc, DocType.LOAN_AGREEMENT)

    sections = {c.source.section for c in chunks}
    assert "SECTION 3. COVENANTS" in sections
    assert "SECTION 5. GOVERNING LAW" in sections


def test_chunk_ids_are_unique_and_reference_doc(sample_docs_dir):
    loader = DocumentLoader()
    doc = loader.load(str(sample_docs_dir / "sample_loan_agreement.txt"), doc_type=DocType.LOAN_AGREEMENT)
    chunker = SectionAwareChunker()
    chunks = chunker.chunk_document(doc, DocType.LOAN_AGREEMENT)

    chunk_ids = [c.source.chunk_id for c in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(c.source.doc_id == doc.metadata.doc_id for c in chunks)


def test_section_aware_flags_pii_chunk(sample_docs_dir):
    loader = DocumentLoader()
    doc = loader.load(str(sample_docs_dir / "sample_loan_agreement.txt"), doc_type=DocType.LOAN_AGREEMENT)
    chunker = SectionAwareChunker()
    chunks = chunker.chunk_document(doc, DocType.LOAN_AGREEMENT)

    pii_chunks = [c for c in chunks if c.contains_pii]
    assert len(pii_chunks) >= 1
    for c in pii_chunks:
        assert "[REDACTED:" in c.text


def test_fixed_size_chunker_respects_max_length(sample_docs_dir):
    loader = DocumentLoader()
    doc = loader.load(str(sample_docs_dir / "sample_financial_statement.txt"), doc_type=DocType.FINANCIAL_STATEMENT)
    chunker = FixedSizeChunker(chunk_chars=200, overlap_chars=20)
    chunks = chunker.chunk_document(doc, DocType.FINANCIAL_STATEMENT)

    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


def test_get_chunker_factory():
    assert isinstance(get_chunker(ChunkingStrategy.SECTION_AWARE), SectionAwareChunker)
    assert isinstance(get_chunker("fixed_size"), FixedSizeChunker)
