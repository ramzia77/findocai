from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class AzureLLMConfig(BaseModel):
    deployment: Optional[str] = None
    endpoint: Optional[str] = None
    api_version: str = "2024-08-01-preview"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    azure: AzureLLMConfig = AzureLLMConfig()
    ollama: OllamaConfig = OllamaConfig()


class EmbeddingConfig(BaseModel):
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    azure: AzureLLMConfig = AzureLLMConfig()
    ollama: OllamaConfig = OllamaConfig()


class ChunkingConfig(BaseModel):
    strategy: str = "section_aware"
    max_chunk_chars: int = 1500
    overlap_chars: int = 150


class VectorstoreConfig(BaseModel):
    backend: str = "faiss"
    index_path: str = "vectorstore/data/findocai.faiss"


class RetrievalConfig(BaseModel):
    top_k: int = 5


class RedactionConfig(BaseModel):
    engine: str = "regex"
    store_raw_text: bool = True


class AuditConfig(BaseModel):
    backend: str = "jsonl"
    path: str = "logs/audit.jsonl"


class PathsConfig(BaseModel):
    sample_docs_dir: str = "sample_docs"
    index_dir: str = "vectorstore/data"
    logs_dir: str = "logs"


class ApiConfig(BaseModel):
    keys: list[str] = ["dev-local-key"]


class Settings(BaseSettings):
    """Central config: static values load from config.yaml, secrets/env-specific
    overrides load from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # env-backed secrets
    openai_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    findocai_api_keys: Optional[str] = None
    findocai_env: str = "local"

    # yaml-backed config
    llm: LLMConfig = LLMConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    vectorstore: VectorstoreConfig = VectorstoreConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    redaction: RedactionConfig = RedactionConfig()
    audit: AuditConfig = AuditConfig()
    paths: PathsConfig = PathsConfig()
    api: ApiConfig = ApiConfig()

    @property
    def api_keys(self) -> list[str]:
        if self.findocai_api_keys:
            return [k.strip() for k in self.findocai_api_keys.split(",") if k.strip()]
        return self.api.keys

    @property
    def has_llm_credentials(self) -> bool:
        if self.llm.provider == "azure_openai":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        if self.llm.provider == "openai":
            return bool(self.openai_api_key)
        return True  # fake provider

    @property
    def has_embedding_credentials(self) -> bool:
        if self.embedding.provider == "azure_openai":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        if self.embedding.provider == "openai":
            return bool(self.openai_api_key)
        return True  # fake provider


def load_settings(config_path: str | Path = BASE_DIR / "config.yaml") -> Settings:
    yaml_data = {}
    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    kwargs = {}
    for key in ("llm", "embedding", "chunking", "vectorstore", "retrieval", "redaction", "audit", "paths", "api"):
        if key in yaml_data:
            kwargs[key] = yaml_data[key]

    return Settings(**kwargs)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
