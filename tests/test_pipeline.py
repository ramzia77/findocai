import pytest

from db.session import init_db
from ingestion.pipeline import _embed_with_cache


class _CountingEmbedder:
    """Wraps a real embedding call pattern but counts how many texts were
    actually sent to embed_texts, so tests can prove the cache is skipping
    redundant calls rather than just trusting it silently."""

    def __init__(self, dimensions: int = 8):
        self._dimensions = dimensions
        self.embed_calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [[float(len(t))] * self._dimensions for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return "counting-fake"


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db("sqlite:///:memory:")


def test_embed_with_cache_skips_previously_embedded_text():
    embedder = _CountingEmbedder()

    first = _embed_with_cache(embedder, ["hello", "world"])
    assert len(embedder.embed_calls) == 1
    assert embedder.embed_calls[0] == ["hello", "world"]

    second = _embed_with_cache(embedder, ["hello", "world"])
    # No new embed_texts call at all -- everything was cached.
    assert len(embedder.embed_calls) == 1
    assert second == first


def test_embed_with_cache_only_embeds_the_new_text():
    embedder = _CountingEmbedder()

    _embed_with_cache(embedder, ["alpha", "beta"])
    _embed_with_cache(embedder, ["alpha", "gamma"])

    # Second call should only have sent "gamma" (new), not "alpha" (cached).
    assert embedder.embed_calls[1] == ["gamma"]


def test_embed_with_cache_falls_back_without_a_database():
    # No init_db() call for this specific check -- simulate a caller that
    # never set up a database at all.
    from db import session as db_session

    db_session._engine = None
    db_session._SessionLocal = None

    embedder = _CountingEmbedder()
    result = _embed_with_cache(embedder, ["x"])
    assert result == [[1.0] * embedder.dimensions]
    assert len(embedder.embed_calls) == 1
