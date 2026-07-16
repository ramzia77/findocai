from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum

from ingestion.cleaner import PIIRedactor, TextCleaner, get_redactor
from ingestion.loader import LoadedDocument
from ingestion.metadata import Chunk, DocType, SourceRef

# Matches common legal/financial document headings: "Section 4.2", "ARTICLE III",
# "1. Definitions", all-caps headings on their own line.
_SECTION_HEADING = re.compile(
    r"^(?:"
    r"(?:SECTION|Section|Article|ARTICLE)\s+[\dIVXLC]+[.:]?.*"
    r"|\d+(?:\.\d+)*\.\s+[A-Z][^\n]{0,80}"
    r"|[A-Z][A-Z0-9 ,'/&-]{4,80}"
    r")$",
    re.MULTILINE,
)


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    SECTION_AWARE = "section_aware"


class BaseChunker(ABC):
    def __init__(self, redactor: PIIRedactor | None = None):
        self.redactor = redactor or get_redactor()
        self.cleaner = TextCleaner()

    @abstractmethod
    def chunk_document(self, loaded_doc: LoadedDocument, doc_type: DocType) -> list[Chunk]:
        ...

    def _make_chunk(
        self,
        raw_text: str,
        doc_id: str,
        filename: str,
        page_number: int,
        section: str | None,
        index: int,
        char_start: int,
        char_end: int,
        doc_type: DocType,
    ) -> Chunk:
        redacted_text, matches = self.redactor.redact(raw_text)
        source = SourceRef(
            doc_id=doc_id,
            filename=filename,
            page_number=page_number,
            section=section,
            chunk_id=f"{doc_id}::p{page_number}::c{index}",
            char_start=char_start,
            char_end=char_end,
        )
        return Chunk(
            text=redacted_text,
            raw_text=raw_text,
            source=source,
            doc_type=doc_type,
            contains_pii=len(matches) > 0,
        )


class SectionAwareChunker(BaseChunker):
    """Splits on detected headings/clauses, falls back to paragraph boundaries,
    then hard-splits any chunk still over max_chunk_chars at a sentence boundary."""

    def __init__(
        self,
        max_chunk_chars: int = 1500,
        overlap_chars: int = 150,
        redactor: PIIRedactor | None = None,
    ):
        super().__init__(redactor=redactor)
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, loaded_doc: LoadedDocument, doc_type: DocType) -> list[Chunk]:
        chunks: list[Chunk] = []
        index = 0
        for page in loaded_doc.pages:
            text = self.cleaner.normalize(page.text)
            if not text:
                continue
            for section_heading, start, end in self._detect_sections(text):
                section_text = text[start:end]
                for piece_start, piece_end in self._split_to_max_len(section_text):
                    piece = section_text[piece_start:piece_end]
                    if not piece.strip():
                        continue
                    chunks.append(
                        self._make_chunk(
                            raw_text=piece,
                            doc_id=loaded_doc.metadata.doc_id,
                            filename=loaded_doc.metadata.filename,
                            page_number=page.page_number,
                            section=section_heading,
                            index=index,
                            char_start=start + piece_start,
                            char_end=start + piece_end,
                            doc_type=doc_type,
                        )
                    )
                    index += 1
        return chunks

    def _detect_sections(self, page_text: str) -> list[tuple[str | None, int, int]]:
        headings = list(_SECTION_HEADING.finditer(page_text))
        if not headings:
            return [(None, 0, len(page_text))]

        sections: list[tuple[str | None, int, int]] = []
        if headings[0].start() > 0:
            sections.append((None, 0, headings[0].start()))

        for i, match in enumerate(headings):
            start = match.start()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(page_text)
            heading_text = match.group().strip()
            sections.append((heading_text, start, end))

        return sections

    def _split_to_max_len(self, text: str) -> list[tuple[int, int]]:
        if len(text) <= self.max_chunk_chars:
            return [(0, len(text))]

        spans: list[tuple[int, int]] = []
        cursor = 0
        while cursor < len(text):
            end = min(cursor + self.max_chunk_chars, len(text))
            if end < len(text):
                boundary = text.rfind(". ", cursor, end)
                if boundary != -1 and boundary > cursor:
                    end = boundary + 1
            spans.append((cursor, end))
            if end >= len(text):
                break
            cursor = max(end - self.overlap_chars, cursor + 1)
        return spans


class FixedSizeChunker(BaseChunker):
    """Naive fixed-length chunker used only as a baseline for A/B comparison
    against SectionAwareChunker in evaluation/chunking_ab.py."""

    def __init__(
        self,
        chunk_chars: int = 1000,
        overlap_chars: int = 100,
        redactor: PIIRedactor | None = None,
    ):
        super().__init__(redactor=redactor)
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, loaded_doc: LoadedDocument, doc_type: DocType) -> list[Chunk]:
        chunks: list[Chunk] = []
        index = 0
        for page in loaded_doc.pages:
            text = self.cleaner.normalize(page.text)
            if not text:
                continue
            cursor = 0
            while cursor < len(text):
                end = min(cursor + self.chunk_chars, len(text))
                piece = text[cursor:end]
                if piece.strip():
                    chunks.append(
                        self._make_chunk(
                            raw_text=piece,
                            doc_id=loaded_doc.metadata.doc_id,
                            filename=loaded_doc.metadata.filename,
                            page_number=page.page_number,
                            section=None,
                            index=index,
                            char_start=cursor,
                            char_end=end,
                            doc_type=doc_type,
                        )
                    )
                    index += 1
                if end >= len(text):
                    break
                cursor = max(end - self.overlap_chars, cursor + 1)
        return chunks


def get_chunker(strategy: ChunkingStrategy | str, **kwargs) -> BaseChunker:
    strategy = ChunkingStrategy(strategy)
    if strategy == ChunkingStrategy.SECTION_AWARE:
        return SectionAwareChunker(**kwargs)
    if strategy == ChunkingStrategy.FIXED_SIZE:
        return FixedSizeChunker(**kwargs)
    raise ValueError(f"Unsupported chunking strategy: {strategy!r}")
