# findocai

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)
![React](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-61DAFB)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

A financial-document AI pipeline for a bank: ingest loan agreements,
invoices, KYC forms, and financial statements, then either **ask questions
with cited answers** or **extract structured fields** into JSON. Built as a
portfolio piece with the same shape as a real contract-review / KYC-triage
assistant, including PII/PCI redaction and audit logging since a bank
context makes those non-optional.

## Features

- **Cited Q&A** -- ask natural-language questions over ingested documents
  and get answers with clickable citations back to the exact page/section
  they came from.
- **Structured extraction** -- pull fields (interest rate, parties, amounts,
  dates, etc.) out of a document into JSON, per document type.
- **PII/PCI redaction** -- SSNs, credit cards, bank account/routing numbers,
  emails, phones, and EINs are redacted before anything reaches an LLM.
- **Audit logging** -- every query/extraction is logged to a JSONL trail
  independent of application logs, for compliance review.
- **Pluggable providers** -- runs fully offline with `Fake*` clients for
  tests, locally for free on **Ollama**, or against OpenAI/Azure OpenAI --
  no code changes, just `config.yaml`.
- **React + TypeScript web UI** -- Upload and Ask screens against the API,
  buildable as a single deployable served by FastAPI itself.

## Architecture

```
sample_docs/*.txt|*.pdf
        |
        v
+------------------+     +-------------------+     +------------------+
|  ingestion/       | --> |  ingestion/        | --> |  ingestion/       |
|  loader.py         |     |  cleaner.py         |     |  chunker.py        |
|  (pdfplumber/OCR)  |     |  (normalize + PII   |     |  (section-aware or |
|                     |     |   redaction)        |     |   fixed-size)      |
+------------------+     +-------------------+     +--------+---------+
                                                              |
                                                              v Chunk(text=redacted,
                                                                     raw_text, SourceRef)
                                                              |
                                                              v
                                              +-------------------------+
                                              | vectorstore/embedder.py |
                                              | (OpenAI / Azure / Fake) |
                                              +-----------+-------------+
                                                          |
                                                          v
                                              +-------------------------+
                                              |  vectorstore/index.py    |
                                              |  FaissVectorStore         |
                                              |  (+ JSONL metadata        |
                                              |   sidecar, id-aligned)    |
                                              +-----------+-------------+
                                                          |
                                                          v
                                              +-------------------------+
                                              | vectorstore/retriever.py |
                                              +-----------+-------------+
                                                          |
                              +----------------------------+----------------------------+
                              v                                                         v
                  +-------------------+                                   +------------------------+
                  |  rag/chain.py      |                                   |  rag/extractor.py        |
                  |  RAGChain          |                                   |  StructuredExtractor      |
                  |  (cited Q&A)       |                                   |  (function-calling JSON)  |
                  +-----------+---------+                                   +------------+-------------+
                              |                                                         |
                              +----------------------------+----------------------------+
                                                          v
                                              +-------------------------+
                                              |  api/main.py (FastAPI)   |
                                              |  /ingest /query /extract |
                                              |  /health                 |
                                              +-----------+-------------+
                                                          |
                                              +-------------------------+
                                              | api/auth.py               |
                                              | API-key auth +             |
                                              | AuditMiddleware ->          |
                                              | logs/audit.jsonl            |
                                              +-------------------------+
```

Every citation-bearing object (`SourceRef`: doc_id, filename, page_number,
section, chunk_id, char_start, char_end) is defined once in
`ingestion/metadata.py` and flows unchanged through every layer above, so an
API response's citation always traces back to the exact chunk it came from.

**LLM/embedding provider** is abstracted behind `LLMClient` (`rag/chain.py`)
and `EmbeddingClient` (`vectorstore/embedder.py`) protocols, each with
OpenAI, Azure OpenAI, **Ollama** (local, free, no API key), and Fake
(offline) implementations, selected via `config.yaml`. Ollama is the
default provider (see "Running it for real, for free" below).

**Vector store** is abstracted behind a `VectorStore` protocol
(`vectorstore/index.py`), currently backed by local FAISS. Because chunk
metadata is stored as full `Chunk` objects (not reshaped), swapping in
`AzureAISearchVectorStore` or `PineconeVectorStore` later would not require
touching `rag/` at all.

## What runs offline (no API key needed)

This repo is fully wired and testable without any credentials:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip     # old bundled pip resolvers can hang/backtrack badly on
                                                        # the ragas -> langchain dependency tree; upgrade first
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pytest -q                              # 33 tests, all offline via Fake* clients
.venv\Scripts\python -m scripts.ingest_sample_docs --dry-run   # builds a FAISS index with fake embeddings
.venv\Scripts\uvicorn api.main:app --reload            # boots and serves /health, /query, /extract with Fake* clients
.venv\Scripts\python -m evaluation.chunking_ab          # retrieval hit-rate A/B, illustrative only without real embeddings
```

Without `OPENAI_API_KEY` / Azure OpenAI credentials set, `Settings` detects
this and every factory (`get_embedding_client`, `get_llm_client`) falls back
to the deterministic `FakeEmbeddingClient` / `FakeLLMClient` automatically --
nothing crashes, but answers/extractions are canned, not real.

## Running it for real, for free (Ollama, the default)

`config.yaml` defaults `llm.provider` / `embedding.provider` to `ollama` --
fully local, zero cost, no API key, works offline once models are pulled.

1. Install [Ollama](https://ollama.com) (`winget install Ollama.Ollama` on
   Windows) and make sure `ollama serve` is running (it usually starts
   automatically as a background service after install).
2. Pull the two models `config.yaml` expects:
   ```
   ollama pull llama3.2:3b        # chat + function/tool calling (~2GB; llama3.1:8b is higher-quality but ~4.9GB)
   ollama pull nomic-embed-text   # embeddings
   ```
3. Install system dependencies for OCR (only needed for scanned PDFs; the
   vendored `.txt` sample docs need neither):
   - Windows: `winget install UB-Mannheim.TesseractOCR` and
     `winget install oschwartz10612.Poppler`, then make sure both install
     directories end up on `PATH` (the Tesseract installer may not add
     itself automatically -- add `C:\Program Files\Tesseract-OCR` manually
     if `tesseract --version` doesn't work in a new terminal).
   - Docker: already handled by the `Dockerfile` (`tesseract-ocr`,
     `poppler-utils`).
4. `pip install -r requirements.txt`
5. Build a real-embedding index: `python -m scripts.ingest_sample_docs`
6. Serve the API: `uvicorn api.main:app --reload`
7. Query it:
   ```bash
   curl -X POST http://localhost:8000/query \
     -H "X-API-Key: dev-local-key" -H "Content-Type: application/json" \
     -d '{"question": "What is the interest rate on the loan?"}'

   curl -X POST http://localhost:8000/extract \
     -H "X-API-Key: dev-local-key" -H "Content-Type: application/json" \
     -d '{"doc_id": "<doc_id from ingest output>", "doc_type": "loan_agreement"}'
   ```

`dev-local-key` is the default accepted API key from `config.yaml` /
`.env.example` -- change `FINDOCAI_API_KEYS` for anything beyond local use.

**`evaluation/ragas_eval.py` still needs an OpenAI key** even in the Ollama
setup above -- `ragas` uses its own LLM-as-judge internally (not our
`LLMClient` abstraction) and only knows how to talk to OpenAI/Azure OpenAI.
Set `OPENAI_API_KEY` in `.env` if you want real faithfulness/relevancy
scores; everything else (Q&A, extraction, the web UI) works fully on Ollama.

**To use OpenAI or Azure OpenAI instead of Ollama**: set `llm.provider` /
`embedding.provider` to `openai` or `azure_openai` in `config.yaml`, copy
`.env.example` to `.env`, and fill in `OPENAI_API_KEY` (or the
`AZURE_OPENAI_*` trio).

## Web UI

`web/` is a React + Vite + TypeScript + Tailwind single-page app (enterprise
dashboard styling) covering the Upload and Ask flows against the API above.

```powershell
cd web
npm install
npm run dev             # serves on http://localhost:5173
```

Open the app, go to **Settings**, and set the API base URL (defaults to
`http://localhost:8000`) and API key (`dev-local-key` for local testing) --
these are stored in the browser's `localStorage`, never hardcoded. Then use
**Upload** to ingest a document and **Ask** to query it; answers render with
clickable `[1]`/`[2]` citation badges that scroll to the matching source
card. The backend has `CORSMiddleware` enabled (permissive origins for local
dev -- tighten `allow_origins` in `api/main.py` before any real deployment)
so the Vite dev server can call the API directly.

For a single-deployable setup, `npm run build` produces `web/dist`; if that
directory exists, `api/main.py` automatically mounts it at `/` (registered
after all API routes, so `/health`, `/query`, `/ingest`, `/extract` still
resolve first), so `uvicorn api.main:app` alone then serves both the API and
the built UI with no CORS needed at all.

## Compliance & production hardening

- **PII/PCI redaction** (`ingestion/cleaner.py`): SSN, credit card (Luhn
  checked), bank account/routing numbers (ABA checksum), email, phone, and
  EIN patterns are redacted at chunk-creation time, before anything is
  embedded or sent to an LLM. The original text is retained separately
  (`Chunk.raw_text`) for authenticated citation display and can be disabled
  via `config.yaml: redaction.store_raw_text: false`. Swapping the regex
  engine for Microsoft Presidio later only requires a new class implementing
  `find`/`redact`.
- **Auth**: hashed, scoped (`upload`/`query`/`read`/`admin`), per-tenant API
  keys with constant-time comparison (`api/auth.py`) -- not one flat shared
  secret. `python -m scripts.hash_api_key` generates a key hash so the
  plaintext never has to live in config.
- **Rate limiting**: per-key token-bucket ASGI middleware (`api/rate_limit.py`).
- **Real database**: SQLite via SQLAlchemy (`db/`) is the system of record
  for the document registry, audit trail, and embedding cache -- WAL mode
  for real concurrent-write safety, replacing the JSONL files that had none.
  One connection-string change (`config.yaml: database.url`) migrates to
  Postgres.
- **Encryption at rest** (`encryption.py`): optional Fernet encryption for
  audit-log question/answer text and each chunk's `raw_text`, enabled by
  setting `FINDOCAI_ENCRYPTION_KEY`. No-op (plaintext) if unset.
- **Multi-tenancy**: each API key carries a `tenant_id`; documents, audit
  records, and retrieval/search results are all scoped to it, so a
  compromised key only ever exposes its own tenant's data.
- **Audit logging**: every `/query`/`/extract` call is recorded (who, when,
  what was retrieved, what was answered, latency) in the database (queryable
  via `GET /audit`), plus a legacy JSONL export at `logs/audit.jsonl` --
  deliberately separate from application logs.
- **Observability**: structured JSON logs (`logging_config.py`) correlated
  by `request_id` across app logs and audit records; `GET /ready` checks real
  dependency health (DB, vectorstore, LLM provider) separately from `GET
  /health` (liveness only); optional Sentry via `SENTRY_DSN`.
- **Right to erasure**: `DELETE /documents/{doc_id}` actually removes a
  document's vectors (via FAISS `reconstruct_n`, no re-embedding needed) and
  its registry row -- no more `NotImplementedError`.

See **[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)** for the
full audit this hardening pass responded to, and what's left (real SSO/OIDC,
CDN, load balancer, managed KMS, off-site backups, malware scanning) --
those need actual infrastructure this repo doesn't provide on its own.

## Migration path

- FAISS -> Azure AI Search / Pinecone / pgvector: implement the
  `VectorStore` protocol in `vectorstore/index.py`; `rag/chain.py` and
  `rag/extractor.py` never touch FAISS directly. Note this is also the
  remaining piece for true horizontal scaling -- the DB layer is safe for
  multiple replicas now, but the FAISS index itself is still per-process
  memory.
- SQLite -> Postgres: change `database.url` in `config.yaml`; SQLAlchemy
  abstracts the rest.
- FastAPI -> Azure Container Apps / Azure Functions: `api/main.py` builds all
  state in `lifespan` and stores it on `app.state`, with no global mutable
  singletons besides the loaded index -- suited to stateless-handler
  deployment.

## Repository layout

- `ingestion/` -- `loader.py` (PDF/OCR/txt), `cleaner.py` (normalize + PII
  redaction), `chunker.py` (section-aware / fixed-size), `metadata.py`
  (shared citation/chunk models), `pipeline.py` (shared ingest orchestration
  + embedding cache).
- `vectorstore/` -- `embedder.py`, `index.py` (FAISS, tenant-aware search +
  real delete), `retriever.py`.
- `rag/` -- `chain.py` (LLM client + cited Q&A), `extractor.py` (structured
  extraction), `prompts/` (system prompt templates).
- `api/` -- `main.py` (FastAPI app), `schemas.py`, `auth.py` (scoped API-key
  auth + audit logging), `rate_limit.py` (token-bucket middleware).
- `db/` -- `models.py`, `session.py`, `repository.py` (SQLAlchemy: document
  registry, audit trail, embedding cache).
- `encryption.py`, `logging_config.py` -- encryption-at-rest and structured
  logging, both root-level alongside `settings.py`.
- `evaluation/` -- `test_set.json`, `ragas_eval.py`, `chunking_ab.py`.
- `scripts/ingest_sample_docs.py`, `scripts/hash_api_key.py` -- ingestion CLI
  and API-key hashing helper.
- `sample_docs/` -- synthetic public-style loan agreement, invoice, and
  10-K excerpt (see `sample_docs/README.md`).
- `tests/` -- offline unit/integration tests using `Fake*` clients and an
  in-memory SQLite DB per test.
- `web/` -- React + Vite + TypeScript + Tailwind UI; `src/api/types.ts`
  mirrors the Pydantic schemas, `src/api/client.ts` is the fetch wrapper.

## License

[MIT](LICENSE)
