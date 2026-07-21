# Production readiness — what changed, and what's still needed

This document is the record of a specific exercise: an architecture/security
audit was run against `findocai` as if it were about to touch real bank
loan/PII data, and this describes what was fixed in response, plus what
genuinely still requires infrastructure this repo can't provide on its own
(a real cloud account, a load balancer, an SSO provider, etc.).

## What was fixed

### Security
- **Constant-time API key comparison** (`api/auth.py`) -- was a plain `!=`,
  a timing side-channel.
- **Hashed, scoped, per-tenant API keys** -- was one shared plaintext
  secret with full access to everything. Now: SHA-256 hashes at rest
  (`scripts/hash_api_key.py` generates one), scopes (`upload`/`query`/`read`/
  `admin`) enforced per-endpoint via `require_scope(...)`, and a `tenant_id`
  isolating what each key can see.
- **No more default-credential footgun** -- `settings.py` refuses to start
  with the bundled `dev-local-key` outside `findocai_env=local`.
- **CORS allowlist** -- was `allow_origins=["*"]`; now `config.yaml: cors.allowed_origins`,
  defaulting to just the local Vite origin.
- **Upload hardening** (`api/main.py` `/ingest`) -- size limit
  (`config.yaml: upload.max_bytes`) enforced while streaming to disk, plus a
  magic-byte/decodability check so a renamed file can't slip past the
  extension check.
- **Rate limiting** (`api/rate_limit.py`) -- per-API-key token bucket,
  in-process. A real multi-instance deployment should move this to Redis so
  the limit is enforced across replicas, not per-replica.
- **Encryption at rest** (`encryption.py`) -- optional Fernet encryption for
  audit question/answer text and each chunk's `raw_text`. No-op without
  `FINDOCAI_ENCRYPTION_KEY` set (not a silent regression -- it's opt-in,
  same posture as before this existed).
- **Right to erasure** -- `FaissVectorStore.delete()` used to
  `raise NotImplementedError`. Now it actually removes the target document's
  vectors (via FAISS `reconstruct_n`, no re-embedding) and its DB row, wired
  to `DELETE /documents/{doc_id}`.

### Data & concurrency
- **Real database** (`db/`) -- SQLite via SQLAlchemy, WAL mode. Replaces
  JSONL files with no transactional guarantees and no concurrent-write
  safety (two simultaneous `/ingest` calls could previously race on the same
  file). Now the system of record for the document registry, the audit
  trail, and an embedding cache (skips re-embedding unchanged chunk text).
  One connection-string change (`config.yaml: database.url`) migrates to
  Postgres -- SQLAlchemy abstracts the rest.
- **Multi-tenancy** -- `Chunk.tenant_id`, threaded through ingestion,
  `FaissVectorStore.search()`, `Retriever.retrieve()`, and
  `StructuredExtractor.extract()`, mirrors the existing `doc_type` filter
  pattern. Documents and audit records are scoped the same way.

### Observability
- **Structured JSON logs** (`logging_config.py`) with a `request_id`
  correlating every log line to the audit record for the same request.
- **Real readiness check** -- `GET /ready` verifies DB connectivity,
  vectorstore load state, and (for Ollama) LLM reachability, separate from
  `GET /health` (liveness -- process up, nothing else).
- **Optional Sentry** -- `sentry_sdk.init()` only if `SENTRY_DSN` is set.

## What's deliberately not built here (needs real infrastructure)

| Area | What's needed | Where it plugs in |
|---|---|---|
| Real SSO/OIDC | Auth0 / Azure AD / Okta instead of API keys | `api/auth.py`'s `require_scope` would resolve an `AuthContext` from a verified JWT instead of a hashed key |
| CDN | CloudFront / Cloudflare / Azure Front Door in front of the built web UI | `web/dist` is already a static, hashed-filename bundle -- just needs a CDN origin |
| Load balancer + multiple replicas | A real LB (ALB, Azure App Gateway, nginx) | Safe for the DB layer now (WAL + real transactions); the FAISS index is still per-process memory, so true horizontal *search* scaling needs the managed-vector-DB migration below first |
| Managed vector DB | Azure AI Search / Pinecone / pgvector | Implement the `VectorStore` protocol in `vectorstore/index.py`; `rag/chain.py`/`rag/extractor.py` never touch FAISS directly |
| Managed KMS | AWS KMS / Azure Key Vault instead of a local Fernet key in an env var | `encryption.py`'s `_get_fernet()` is the one place that would change |
| Malware scanning | ClamAV (or a cloud AV API) on `/ingest` | Would sit right after the existing size/magic-byte check in `api/main.py` |
| Off-site/automated backups | A scheduled job shipping the SQLite file + FAISS index files to object storage | Much simpler than before this migration -- it's now two files, not an ever-growing JSONL plus an index |
| Rate limiting across replicas | Redis-backed token bucket instead of in-process | `api/rate_limit.py`'s `RateLimitMiddleware` would swap its in-memory `dict` for Redis `INCR`/`EXPIRE` |

## Verification

- `pytest -q` -- 65 tests, all offline (in-memory SQLite per test, `Fake*`
  LLM/embedding clients).
- Manual: start the Ollama-backed backend, confirm `GET /ready` reflects
  real dependency health, ingest a document, confirm it's visible via
  `GET /documents`, delete it and confirm it's gone from both the registry
  and retrieval, confirm a key without the `admin` scope gets `403` on
  delete, confirm rate limiting returns `429` under rapid repeated requests.
