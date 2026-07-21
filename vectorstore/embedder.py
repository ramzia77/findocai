from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def model(self) -> str:
        """Identifies which model produced a vector -- used as part of the
        embedding cache key so two different models can't collide even if
        they happen to share a dimension count."""
        ...


class OpenAIEmbeddingClient:
    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None, dimensions: int = 1536):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return self._model


class AzureOpenAIEmbeddingClient:
    def __init__(self, deployment: str, endpoint: str, api_key: str, api_version: str, dimensions: int = 1536):
        from openai import AzureOpenAI

        self._client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        self._deployment = deployment
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._deployment, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return self._deployment


class OllamaEmbeddingClient:
    """Local, free embeddings via a running Ollama server (`ollama serve`,
    with the embedding model already pulled, e.g. `ollama pull nomic-embed-text`).
    Uses the batch /api/embed endpoint over plain HTTP -- no API key, no
    additional dependency beyond `requests` (already required)."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dimensions: int = 768,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import requests

        response = requests.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return self._model


class FakeEmbeddingClient:
    """Deterministic hash-based pseudo-embeddings for offline testing and
    dry-run mode -- no network access, no API key required."""

    def __init__(self, dimensions: int = 64):
        self._dimensions = dimensions

    def _hash_vector(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self._dimensions)
        vec = vec / np.linalg.norm(vec)
        return vec.tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._hash_vector(text)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return "fake"


def get_embedding_client(settings) -> EmbeddingClient:
    provider = settings.embedding.provider
    if provider == "fake" or not settings.has_embedding_credentials:
        return FakeEmbeddingClient(dimensions=settings.embedding.dimensions)
    if provider == "openai":
        return OpenAIEmbeddingClient(
            model=settings.embedding.model,
            api_key=settings.openai_api_key,
            dimensions=settings.embedding.dimensions,
        )
    if provider == "azure_openai":
        return AzureOpenAIEmbeddingClient(
            deployment=settings.embedding.azure.deployment,
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.embedding.azure.api_version,
            dimensions=settings.embedding.dimensions,
        )
    if provider == "ollama":
        return OllamaEmbeddingClient(
            model=settings.embedding.model,
            base_url=settings.embedding.ollama.base_url,
            dimensions=settings.embedding.dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {provider!r}")
