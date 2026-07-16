from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel


class RedactionMatch(BaseModel):
    pii_type: str
    start: int
    end: int


def _luhn_checksum(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _aba_checksum(digits: str) -> bool:
    if len(digits) != 9:
        return False
    weights = [3, 7, 1, 3, 7, 1, 3, 7, 1]
    total = sum(int(d) * w for d, w in zip(digits, weights))
    return total % 10 == 0


DEFAULT_PATTERNS: dict[str, str] = {
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "EIN": r"\b\d{2}-\d{7}\b",
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "PHONE": r"(?<!\d)\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,19}\b",
    "ROUTING_NUMBER": r"(?i)\brouting[^\d\n]{0,15}(\d{9})\b",
    "ACCOUNT_NUMBER": r"(?i)\b(?:account|acct)[^\d\n]{0,15}(\d{8,17})\b",
}


class PIIRedactor:
    """Rule/regex-based redaction. Intentionally the only piece that would need
    replacing with a PresidioRedactor (same find/redact interface) later."""

    def __init__(self, patterns: Optional[dict[str, str]] = None):
        self.patterns = patterns or DEFAULT_PATTERNS
        self._compiled = {k: re.compile(v) for k, v in self.patterns.items()}

    def find(self, text: str) -> list[RedactionMatch]:
        matches: list[RedactionMatch] = []
        for pii_type, pattern in self._compiled.items():
            for m in pattern.finditer(text):
                start, end = m.span(m.lastindex) if m.lastindex else m.span()
                candidate = text[start:end]

                if pii_type == "CREDIT_CARD":
                    digits = re.sub(r"[ -]", "", candidate)
                    if not (13 <= len(digits) <= 19 and digits.isdigit() and _luhn_checksum(digits)):
                        continue
                if pii_type == "ROUTING_NUMBER":
                    if not _aba_checksum(candidate):
                        continue

                matches.append(RedactionMatch(pii_type=pii_type, start=start, end=end))
        matches.sort(key=lambda m: m.start)
        return matches

    def redact(self, text: str, mask: str = "[REDACTED:{type}]") -> tuple[str, list[RedactionMatch]]:
        matches = self.find(text)
        if not matches:
            return text, matches

        out = []
        cursor = 0
        for match in matches:
            if match.start < cursor:
                continue  # overlapping match, skip
            out.append(text[cursor:match.start])
            out.append(mask.format(type=match.pii_type))
            cursor = match.end
        out.append(text[cursor:])
        return "".join(out), matches


def get_redactor(engine: str = "regex") -> PIIRedactor:
    if engine == "regex":
        return PIIRedactor()
    raise ValueError(f"Unsupported redaction engine: {engine!r} (only 'regex' is implemented)")


class TextCleaner:
    """Normalizes raw extracted text before chunking."""

    _hyphen_break = re.compile(r"(\w)-\n(\w)")
    _whitespace = re.compile(r"[ \t]+")
    _blank_lines = re.compile(r"\n{3,}")

    def normalize(self, text: str) -> str:
        text = text.replace("­", "")  # soft hyphen
        text = self._hyphen_break.sub(r"\1\2", text)  # de-hyphenate line-wrapped words
        text = self._whitespace.sub(" ", text)
        text = self._blank_lines.sub("\n\n", text)
        return text.strip()
