from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from ingestion.cleaner import PIIRedactor, get_redactor

API_KEY_HEADER = "X-API-Key"


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER)) -> str:
    """Module-level FastAPI dependency so it can be imported directly and
    overridden in tests via app.dependency_overrides[require_api_key]."""
    from settings import get_settings

    settings = get_settings()
    if not x_api_key or x_api_key not in settings.api_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return x_api_key


def _key_id(api_key: str) -> str:
    return api_key[-4:] if len(api_key) >= 4 else "****"


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


class AuditMiddleware(BaseHTTPMiddleware):
    """Wraps every request; route handlers for /query and /extract stash a
    dict on request.state.audit_extra (question, retrieved_chunk_ids, answer,
    doc_type) before returning, and this middleware combines it with
    request-level info (timing, api key) to write one audit log line. Routes
    that don't set audit_extra (e.g. /health) are not logged."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        audit_extra = getattr(request.state, "audit_extra", None)
        if audit_extra is not None:
            audit_logger: AuditLogger = request.app.state.audit_logger
            api_key = request.headers.get(API_KEY_HEADER, "")
            latency_ms = (time.perf_counter() - start) * 1000
            audit_logger.log_query(
                request_id=request_id,
                api_key_id=_key_id(api_key),
                endpoint=request.url.path,
                question=audit_extra.get("question", ""),
                retrieved_chunk_ids=audit_extra.get("retrieved_chunk_ids", []),
                answer=audit_extra.get("answer", ""),
                timestamp=datetime.now(timezone.utc).isoformat(),
                doc_type=audit_extra.get("doc_type"),
                latency_ms=latency_ms,
                status_code=response.status_code,
            )

        return response
