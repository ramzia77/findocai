from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

ALL_SCOPES = ["upload", "query", "read", "admin"]


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
    backend: str = "sqlite"  # sqlite | jsonl (jsonl kept only as a legacy export path)
    path: str = "logs/audit.jsonl"  # legacy JSONL export target, not the primary store


class PathsConfig(BaseModel):
    sample_docs_dir: str = "sample_docs"
    index_dir: str = "vectorstore/data"
    logs_dir: str = "logs"


class ApiKeyEntry(BaseModel):
    """One issued API key. `key` (plaintext) is the convenient/back-compat
    form for local dev -- it's hashed in memory immediately and never
    compared or logged in plaintext. `key_hash` lets an operator configure a
    key without ever putting the plaintext in config.yaml at all (generate
    one with scripts/hash_api_key.py)."""

    key: Optional[str] = None
    key_hash: Optional[str] = None
    scopes: list[str] = list(ALL_SCOPES)
    tenant_id: str = "default"

    @property
    def resolved_hash(self) -> str:
        if self.key_hash:
            return self.key_hash.lower()
        if self.key:
            return hash_api_key(self.key)
        raise ValueError("ApiKeyEntry requires either 'key' or 'key_hash'")


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class ApiConfig(BaseModel):
    # Plain strings are back-compat sugar for {key: <string>, scopes: ALL, tenant_id: "default"}.
    keys: list[Union[str, ApiKeyEntry]] = ["dev-local-key"]


class CorsConfig(BaseModel):
    # Must be an explicit allowlist outside local dev -- "*" is only safe
    # because it's paired with allow_credentials=False and a bearer-header
    # auth model (no cookies), but it still permits any origin to *read*
    # responses from a browser, which is not appropriate beyond local dev.
    allowed_origins: list[str] = ["http://localhost:5173"]


class UploadConfig(BaseModel):
    max_bytes: int = 25 * 1024 * 1024  # 25 MB


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests_per_minute: int = 60


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./findocai.db"


class ObservabilityConfig(BaseModel):
    sentry_dsn: Optional[str] = None
    log_path: str = "logs/app.log"


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
    findocai_encryption_key: Optional[str] = None
    sentry_dsn: Optional[str] = None
    database_url: Optional[str] = None
    vectorstore_index_path: Optional[str] = None

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
    cors: CorsConfig = CorsConfig()
    upload: UploadConfig = UploadConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    database: DatabaseConfig = DatabaseConfig()
    observability: ObservabilityConfig = ObservabilityConfig()

    def resolved_api_keys(self) -> list[ApiKeyEntry]:
        entries: list[ApiKeyEntry] = []
        for item in self.api.keys:
            if isinstance(item, str):
                entries.append(ApiKeyEntry(key=item))
            else:
                entries.append(item)
        if self.findocai_api_keys:
            for raw in self.findocai_api_keys.split(","):
                raw = raw.strip()
                if raw:
                    entries.append(ApiKeyEntry(key=raw))
        return entries

    @property
    def api_keys(self) -> list[str]:
        """Legacy accessor (plaintext keys only, back-compat for callers that
        haven't moved to resolved_api_keys()). Prefer resolved_api_keys()."""
        if self.findocai_api_keys:
            return [k.strip() for k in self.findocai_api_keys.split(",") if k.strip()]
        return [k for k in self.api.keys if isinstance(k, str)]

    @property
    def is_using_default_credentials(self) -> bool:
        """True if the only configured key is the well-known local-dev
        default -- used to refuse startup outside findocai_env=local."""
        keys = self.resolved_api_keys()
        return len(keys) == 1 and keys[0].key == "dev-local-key"

    @property
    def has_llm_credentials(self) -> bool:
        if self.llm.provider == "azure_openai":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        if self.llm.provider == "openai":
            return bool(self.openai_api_key)
        return True  # fake / ollama provider

    @property
    def has_embedding_credentials(self) -> bool:
        if self.embedding.provider == "azure_openai":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        if self.embedding.provider == "openai":
            return bool(self.openai_api_key)
        return True  # fake / ollama provider


def load_settings(config_path: str | Path = BASE_DIR / "config.yaml") -> Settings:
    yaml_data = {}
    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    kwargs = {}
    for key in (
        "llm", "embedding", "chunking", "vectorstore", "retrieval", "redaction",
        "audit", "paths", "api", "cors", "upload", "rate_limit", "database", "observability",
    ):
        if key in yaml_data:
            kwargs[key] = yaml_data[key]

    # config.yaml's app.env is a fallback default only -- a real FINDOCAI_ENV
    # environment variable always wins (pydantic-settings gives constructor
    # kwargs priority over env vars, so this has to be conditional here
    # rather than just always passing it through).
    app_env = (yaml_data.get("app") or {}).get("env")
    if app_env and "FINDOCAI_ENV" not in os.environ:
        kwargs["findocai_env"] = app_env

    settings = Settings(**kwargs)
    if settings.database_url:
        settings.database.url = settings.database_url
    if settings.vectorstore_index_path:
        settings.vectorstore.index_path = settings.vectorstore_index_path

    if settings.findocai_env != "local" and settings.is_using_default_credentials:
        raise RuntimeError(
            "Refusing to start with the default 'dev-local-key' API key outside "
            "findocai_env=local. Set FINDOCAI_API_KEYS (comma-separated) or "
            "configure api.keys in config.yaml with real keys."
        )

    return settings


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings_cache() -> None:
    """Test-only escape hatch: clears the cached Settings singleton so a new
    call to get_settings() re-reads config.yaml / the environment."""
    global _settings
    _settings = None
