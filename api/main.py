from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.auth import AuditLogger, AuditMiddleware, require_api_key
from api.schemas import (
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from ingestion.chunker import get_chunker
from ingestion.loader import DocumentLoader
from ingestion.metadata import DocType
from ingestion.pipeline import ingest_document
from rag.chain import RAGChain, get_llm_client
from rag.extractor import StructuredExtractor
from settings import BASE_DIR, get_settings
from vectorstore.embedder import get_embedding_client
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

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


app = FastAPI(title="findocai", lifespan=lifespan)
app.add_middleware(AuditMiddleware)
# CORSMiddleware is added last so it wraps outermost (Starlette builds the
# middleware stack in reverse registration order), letting it handle
# preflight OPTIONS requests and attach headers to every response, including
# errors raised by inner middleware/handlers. Origins are permissive for
# local dev with the web/ Vite app; tighten before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        vectorstore_backend=settings.vectorstore.backend,
        llm_provider=settings.llm.provider,
        embedding_provider=settings.embedding.provider,
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile,
    doc_type: DocType = Form(...),
    api_key: str = Depends(require_api_key),
) -> IngestResponse:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".txt", ".pdf"):
        raise HTTPException(status_code=400, detail="Only .txt and .pdf files are supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        try:
            result = ingest_document(
                tmp_path,
                doc_type,
                request.app.state.loader,
                request.app.state.chunker,
                request.app.state.embedder,
                request.app.state.vectorstore,
            )
        except Exception as e:
            # Surface a clean 500 with the actual cause instead of letting an
            # unexpected exception propagate through AuditMiddleware, which
            # can otherwise abort the connection rather than send a response.
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}") from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    settings = request.app.state.settings
    index_path = BASE_DIR / settings.vectorstore.index_path
    request.app.state.vectorstore.persist(str(index_path))

    return IngestResponse(
        doc_id=result.metadata.doc_id,
        doc_type=doc_type,
        num_pages=result.metadata.num_pages,
        num_chunks=result.num_chunks,
        pii_chunks_redacted=result.pii_chunks_redacted,
    )


@app.post("/query", response_model=QueryResponse)
def query(request: Request, req: QueryRequest, api_key: str = Depends(require_api_key)) -> QueryResponse:
    chain: RAGChain = request.app.state.rag_chain
    result = chain.answer(req.question, doc_type=req.doc_type, top_k=req.top_k)

    request.state.audit_extra = {
        "question": req.question,
        "retrieved_chunk_ids": [c.source.chunk_id for c in result.citations],
        "answer": result.answer,
        "doc_type": req.doc_type.value if req.doc_type else None,
    }

    return QueryResponse(answer=result.answer, citations=result.citations)


@app.post("/extract", response_model=ExtractResponse)
def extract(request: Request, req: ExtractRequest, api_key: str = Depends(require_api_key)) -> ExtractResponse:
    extractor: StructuredExtractor = request.app.state.extractor
    try:
        result = extractor.extract(req.doc_id, req.doc_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    request.state.audit_extra = {
        "question": f"extract:{req.doc_id}",
        "retrieved_chunk_ids": [c.source.chunk_id for c in result.citations],
        "answer": result.fields,
        "doc_type": req.doc_type.value,
    }

    return ExtractResponse(
        doc_id=result.doc_id,
        doc_type=result.doc_type,
        fields=result.fields,
        citations=result.citations,
    )


# Serves the built web/ SPA (after `npm run build`) as a single deployable
# alongside the API. Mounted last so /health, /query, /ingest, /extract above
# still match first -- Starlette checks routes in registration order.
_web_dist = BASE_DIR / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
