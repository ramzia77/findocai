from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.auth import AuditLogger, AuditMiddleware, AuthContext, require_scope
from api.rate_limit import RateLimitMiddleware
from api.schemas import (
    AuditResponse,
    DocumentsResponse,
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from db import repository as db_repository
from db.session import get_engine, init_db
from encryption import decrypt_text
from ingestion.chunker import get_chunker
from ingestion.loader import DocumentLoader
from ingestion.metadata import DocType
from ingestion.pipeline import ingest_document
from logging_config import configure_logging
from rag.chain import RAGChain, get_llm_client
from rag.extractor import StructuredExtractor
from settings import BASE_DIR, get_settings
from vectorstore.embedder import get_embedding_client
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever

# PDF and plain-text magic-byte/decodability checks -- a renamed file with
# the wrong extension shouldn't slip past the suffix check in /ingest.
_PDF_MAGIC = b"%PDF-"


def _looks_like_valid_upload(suffix: str, head: bytes, full_path: Path) -> bool:
    if suffix == ".pdf":
        return head.startswith(_PDF_MAGIC)
    if suffix == ".txt":
        try:
            full_path.read_text(encoding="utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def _init_sentry(settings) -> None:
    if not settings.observability.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=settings.observability.sentry_dsn, traces_sample_rate=0.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(str(BASE_DIR / settings.observability.log_path))
    _init_sentry(settings)

    embedder = get_embedding_client(settings)
    llm_client = get_llm_client(settings)
    loader = DocumentLoader()
    chunker = get_chunker(
        settings.chunking.strategy,
        max_chunk_chars=settings.chunking.max_chunk_chars,
        overlap_chars=settings.chunking.overlap_chars,
    )
    vectorstore = FaissVectorStore(dimensions=embedder.dimensions)

    index_path = BASE_DIR / settings.vectorstore.index_path
    if index_path.exists():
        vectorstore.load(str(index_path))

    init_db(settings.database.url)
    if not db_repository.list_documents():
        # One-time backfill for indexes that predate the document-registry
        # DB (e.g. local dev data from before this migration) -- the FAISS
        # sidecar remains the source of truth for chunk content either way.
        for summary in vectorstore.list_documents():
            db_repository.record_document(
                doc_id=summary.doc_id,
                filename=summary.filename,
                doc_type=summary.doc_type.value,
                num_chunks=summary.num_chunks,
                pii_chunks=summary.pii_chunks,
            )

    retriever = Retriever(vectorstore, embedder, top_k=settings.retrieval.top_k)

    app.state.settings = settings
    app.state.embedder = embedder
    app.state.llm_client = llm_client
    app.state.loader = loader
    app.state.chunker = chunker
    app.state.vectorstore = vectorstore
    app.state.retriever = retriever
    app.state.rag_chain = RAGChain(retriever, llm_client)
    app.state.extractor = StructuredExtractor(retriever, llm_client)
    app.state.audit_logger = AuditLogger(path=str(BASE_DIR / settings.audit.path))

    yield


_startup_settings = get_settings()

app = FastAPI(title="findocai", lifespan=lifespan)
app.add_middleware(AuditMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=_startup_settings.rate_limit.requests_per_minute,
    enabled=_startup_settings.rate_limit.enabled,
)
# CORSMiddleware is added last so it wraps outermost (Starlette builds the
# middleware stack in reverse registration order), letting it handle
# preflight OPTIONS requests and attach headers to every response, including
# errors raised by inner middleware/handlers. allowed_origins is an explicit
# config.yaml allowlist (defaults to the local Vite dev origin only) -- no
# more "*" in the default config.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_startup_settings.cors.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _persist_vectorstore(request: Request) -> None:
    settings = request.app.state.settings
    index_path = BASE_DIR / settings.vectorstore.index_path
    request.app.state.vectorstore.persist(str(index_path))


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Liveness: is the process up at all. Does not check dependencies --
    that's /ready. A load balancer/orchestrator should restart the process
    if this fails; it should stop routing traffic (but not restart) if only
    /ready fails."""
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        vectorstore_backend=settings.vectorstore.backend,
        llm_provider=settings.llm.provider,
        embedding_provider=settings.embedding.provider,
    )


@app.get("/ready")
def ready(request: Request) -> JSONResponse:
    """Readiness: are this instance's actual dependencies usable right now
    (database, vectorstore, and -- for Ollama specifically, since it's a
    local process that can be down independent of this API -- the LLM
    provider). A 200 here means real traffic can be served, not just that
    the ASGI process happens to be running."""
    settings = request.app.state.settings
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    checks["vectorstore"] = "ok" if request.app.state.vectorstore is not None else "not loaded"

    if settings.llm.provider == "ollama":
        try:
            import requests

            r = requests.get(f"{settings.llm.ollama.base_url}/api/version", timeout=3)
            checks["llm_provider"] = "ok" if r.ok else f"error: status {r.status_code}"
        except Exception as e:
            checks["llm_provider"] = f"error: {e}"
    else:
        checks["llm_provider"] = "not checked (provider credentials assumed valid at startup)"

    is_ready = all(v == "ok" or v.startswith("not checked") for v in checks.values())
    return JSONResponse(
        {"status": "ready" if is_ready else "degraded", "checks": checks},
        status_code=200 if is_ready else 503,
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile,
    doc_type: DocType = Form(...),
    auth: AuthContext = Depends(require_scope("upload")),
) -> IngestResponse:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".txt", ".pdf"):
        raise HTTPException(status_code=400, detail="Only .txt and .pdf files are supported")

    settings = request.app.state.settings
    max_bytes = settings.upload.max_bytes

    # The temp file handle must be closed (the `with` block exited) before
    # any unlink -- Windows refuses to delete a file that's still open by
    # the current process, unlike POSIX where that's allowed.
    fd, tmp_path_str = tempfile.mkstemp(suffix=suffix)
    tmp_path = Path(tmp_path_str)
    try:
        total = 0
        head = b""
        too_large = False
        with os.fdopen(fd, "wb") as tmp:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    too_large = True
                    break
                if not head:
                    head = chunk[:16]
                tmp.write(chunk)

        if too_large:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {max_bytes} byte upload limit",
            )

        if not _looks_like_valid_upload(suffix, head, tmp_path):
            raise HTTPException(
                status_code=400,
                detail=f"File content doesn't match its {suffix} extension",
            )

        try:
            result = ingest_document(
                str(tmp_path),
                doc_type,
                request.app.state.loader,
                request.app.state.chunker,
                request.app.state.embedder,
                request.app.state.vectorstore,
                tenant_id=auth.tenant_id,
            )
        except Exception as e:
            # Surface a clean 500 with the actual cause instead of letting an
            # unexpected exception propagate through AuditMiddleware, which
            # can otherwise abort the connection rather than send a response.
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)

    _persist_vectorstore(request)
    db_repository.record_document(
        doc_id=result.metadata.doc_id,
        filename=file.filename,
        doc_type=doc_type.value,
        num_chunks=result.num_chunks,
        pii_chunks=result.pii_chunks_redacted,
        tenant_id=auth.tenant_id,
    )

    return IngestResponse(
        doc_id=result.metadata.doc_id,
        doc_type=doc_type,
        num_pages=result.metadata.num_pages,
        num_chunks=result.num_chunks,
        pii_chunks_redacted=result.pii_chunks_redacted,
    )


@app.post("/query", response_model=QueryResponse)
def query(
    request: Request, req: QueryRequest, auth: AuthContext = Depends(require_scope("query"))
) -> QueryResponse:
    chain: RAGChain = request.app.state.rag_chain
    result = chain.answer(req.question, doc_type=req.doc_type, top_k=req.top_k, tenant_id=auth.tenant_id)

    request.state.audit_extra = {
        "question": req.question,
        "retrieved_chunk_ids": [c.source.chunk_id for c in result.citations],
        "answer": result.answer,
        "doc_type": req.doc_type.value if req.doc_type else None,
        "tenant_id": auth.tenant_id,
    }

    return QueryResponse(answer=result.answer, citations=result.citations)


@app.post("/extract", response_model=ExtractResponse)
def extract(
    request: Request, req: ExtractRequest, auth: AuthContext = Depends(require_scope("query"))
) -> ExtractResponse:
    extractor: StructuredExtractor = request.app.state.extractor
    try:
        result = extractor.extract(req.doc_id, req.doc_type, tenant_id=auth.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    request.state.audit_extra = {
        "question": f"extract:{req.doc_id}",
        "retrieved_chunk_ids": [c.source.chunk_id for c in result.citations],
        "answer": result.fields,
        "doc_type": req.doc_type.value,
        "tenant_id": auth.tenant_id,
    }

    return ExtractResponse(
        doc_id=result.doc_id,
        doc_type=result.doc_type,
        fields=result.fields,
        citations=result.citations,
    )


@app.get("/documents", response_model=DocumentsResponse)
def documents(auth: AuthContext = Depends(require_scope("read"))) -> DocumentsResponse:
    return DocumentsResponse(documents=db_repository.list_documents(tenant_id=auth.tenant_id))


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(
    request: Request, doc_id: str, auth: AuthContext = Depends(require_scope("admin"))
) -> None:
    vectorstore = request.app.state.vectorstore
    before = len(vectorstore.list_documents())
    vectorstore.delete(doc_id)
    after = len(vectorstore.list_documents())
    found_in_db = db_repository.delete_document(doc_id)
    if after == before and not found_in_db:
        raise HTTPException(status_code=404, detail=f"No document with doc_id={doc_id!r}")
    _persist_vectorstore(request)


@app.get("/audit", response_model=AuditResponse)
def audit(limit: int = 50, auth: AuthContext = Depends(require_scope("read"))) -> AuditResponse:
    records = db_repository.list_audit(limit=limit, tenant_id=auth.tenant_id)
    for record in records:
        record["question"] = decrypt_text(record["question"])
        record["answer"] = decrypt_text(record["answer"])
    return AuditResponse(records=records)


# Serves the built web/ SPA (after `npm run build`) as a single deployable
# alongside the API. Mounted last so /health, /query, /ingest, /extract above
# still match first -- Starlette checks routes in registration order.
_web_dist = BASE_DIR / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
