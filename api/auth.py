from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from ingestion.cleaner import PIIRedactor, get_redactor
from logging_config import request_id_var

API_KEY_HEADER = "X-API-Key"


@dataclass
class AuthContext:
    """The resolved identity behind a request's API key. Route handlers get
    this (not the raw key) via Depends(require_scope(...)) so they can read
    tenant_id for data isolation without ever touching the key itself."""

    key_id: str  # last 4 chars only, for audit/display -- never the full key
    scopes: list[str] = field(default_factory=list)
    tenant_id: str = "default"


def _key_id(api_key: str) -> str:
    return api_key[-4:] if len(api_key) >= 4 else "****"


def _resolve_auth_context(x_api_key: Optional[str]) -> Optional[AuthContext]:
    from settings import get_settings, hash_api_key

    if not x_api_key:
        return None

    settings = get_settings()
    candidate_hash = hash_api_key(x_api_key)
    for entry in settings.resolved_api_keys():
        # Constant-time comparison -- a naive `==`/`!=` short-circuits on the
        # first differing byte, which leaks timing information an attacker
        # can use to brute-force the key byte-by-byte.
        if secrets.compare_digest(candidate_hash, entry.resolved_hash):
            return AuthContext(key_id=_key_id(x_api_key), scopes=entry.scopes, tenant_id=entry.tenant_id)
    return None


def require_scope(scope: str):
    """FastAPI dependency factory: authenticates the request's X-API-Key and
    requires the resolved key to carry `scope`. Returns the AuthContext so
    route handlers can read tenant_id/key_id. Each endpoint requires the
    scope matching what it actually does (upload/query/read/admin), rather
    than one flat "any valid key can do anything" check."""

    def dependency(x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER)) -> AuthContext:
        ctx = _resolve_auth_context(x_api_key)
        if ctx is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
        if scope not in ctx.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key does not have the required '{scope}' scope",
            )
        return ctx

    return dependency


class AuditLogger:
    """Append-only JSONL audit trail, deliberately separate from application
    logs, so compliance review can retrieve it independently."""

    def __init__(self, path: str = "logs/audit.jsonl", redactor: Optional[PIIRedactor] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or get_redactor()

    def log_query(
        self,
        *,
        request_id: str,
        api_key_id: str,
        endpoint: str,
        question: str,
        retrieved_chunk_ids: list[str],
        answer: str | dict,
        timestamp: str,
        doc_type: Optional[str],
        latency_ms: float,
        status_code: int,
    ) -> None:
        safe_question, _ = self.redactor.redact(question)
        answer_str = json.dumps(answer) if isinstance(answer, dict) else answer
        safe_answer, _ = self.redactor.redact(answer_str)

        record = {
            "request_id": request_id,
            "timestamp": timestamp,
            "endpoint": endpoint,
            "api_key_id": api_key_id,
            "doc_type": doc_type,
            "question": safe_question,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "answer": safe_answer,
            "latency_ms": latency_ms,
            "status_code": status_code,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


class AuditMiddleware:
    """Wraps every request; route handlers for /query and /extract stash a
    dict on request.state.audit_extra (question, retrieved_chunk_ids, answer,
    doc_type) before returning, and this middleware combines it with
    request-level info (timing, api key) to write one audit log line. Routes
    that don't set audit_extra (e.g. /health) are not logged.

    Implemented as a plain ASGI middleware, NOT starlette.middleware.base
    .BaseHTTPMiddleware -- that class is known to deadlock when it wraps a
    synchronous route handler that runs long enough in FastAPI's threadpool
    (exactly our /query and /extract case with a real, slow LLM call; our
    test suite never caught this because FakeLLMClient resolves in
    milliseconds, too fast to hit the race)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request_id_token = request_id_var.set(request_id)
        start = time.perf_counter()
        response_status: dict[str, int] = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(request_id_token)

        audit_extra = getattr(request.state, "audit_extra", None)
        if audit_extra is not None:
            audit_logger: AuditLogger = scope["app"].state.audit_logger
            api_key = request.headers.get(API_KEY_HEADER, "")
            key_id = _key_id(api_key)
            latency_ms = (time.perf_counter() - start) * 1000
            timestamp = datetime.now(timezone.utc).isoformat()
            question = audit_extra.get("question", "")
            retrieved_chunk_ids = audit_extra.get("retrieved_chunk_ids", [])
            answer = audit_extra.get("answer", "")
            doc_type = audit_extra.get("doc_type")
            status_code = response_status.get("code", 0)

            # Legacy JSONL export (audit_logger does its own redaction).
            audit_logger.log_query(
                request_id=request_id,
                api_key_id=key_id,
                endpoint=request.url.path,
                question=question,
                retrieved_chunk_ids=retrieved_chunk_ids,
                answer=answer,
                timestamp=timestamp,
                doc_type=doc_type,
                latency_ms=latency_ms,
                status_code=status_code,
            )

            # Primary, queryable store -- backs GET /audit. Redacted
            # independently here since AuditLogger's redaction is internal
            # to its own JSONL-writing path. Encrypted at rest if
            # FINDOCAI_ENCRYPTION_KEY is set (encrypt_text is a no-op
            # otherwise) -- redact first, then encrypt, so what's on disk is
            # never plaintext PII even transiently.
            from db import repository as db_repository
            from encryption import encrypt_text

            redactor = get_redactor()
            safe_question, _ = redactor.redact(question)
            answer_str = json.dumps(answer) if isinstance(answer, dict) else str(answer)
            safe_answer, _ = redactor.redact(answer_str)
            db_repository.log_audit(
                request_id=request_id,
                timestamp=timestamp,
                endpoint=request.url.path,
                api_key_id=key_id,
                tenant_id=audit_extra.get("tenant_id", "default"),
                doc_type=doc_type,
                question=encrypt_text(safe_question),
                retrieved_chunk_ids=retrieved_chunk_ids,
                answer=encrypt_text(safe_answer),
                latency_ms=latency_ms,
                status_code=status_code,
            )
