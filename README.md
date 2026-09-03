# Multimodal RAG Application with Guardrails, Evaluations, and Database Migrations

FastAPI backend for authenticated, multimodal PDF question answering. It uses OpenAI for planning,
answering, and vision; Cohere for embeddings and reranking; Qdrant for vector search; PostgreSQL
for users and document metadata; and optional Redis for semantic answer caching.

## Capabilities

- JWT authentication with `user` and `admin` roles, password hashing, and `/me`.
- Admin-only PDF upload, repository batch processing, and document deletion. Authenticated users can
  list documents. Duplicate files are skipped by SHA-256 hash.
- PDF text and page-image ingestion for multimodal retrieval.
- Hybrid dense and sparse Qdrant search with reciprocal-rank fusion, Cohere reranking, query
  rewriting, source-page expansion, and grounded answer generation.
- LangGraph multi-intent orchestration with parallel branches:
  - `lookup` for facts and explanations
  - `list_all` for complete numbered or itemized lists
  - `summarize` for documents or page ranges, including large-document batching
  - `visual` for charts, diagrams, photos, and scanned pages
- Answer grounding and completeness checks with corrective retrieval retries, plus optional Redis
  caching. `/chat` returns `answer` and `cached`.
- NeMo Guardrails input topic gating, with an OpenAI classifier fallback. Off-topic questions are
  refused before routing. Processing documents regenerates allowed topics, answering rules, and the
  evaluation dataset from the current documents.
- Local evaluations for guardrail routing accuracy and RAG keyword recall.
- Alembic-managed PostgreSQL schema migrations.
- Swagger UI at `/docs`, ReDoc at `/redoc`, and `/health`.

## Requirements

- Python 3.11+
- PostgreSQL 14+
- Qdrant
- OpenAI and Cohere API keys
- Redis only when `CACHE_ENABLED=true`

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env` in the project root:

```dotenv
OPENAI_API_KEY=your-openai-api-key
COHERE_API_KEY=your-cohere-api-key
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
SYNC_DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
QDRANT_URL=http://localhost:6333
JWT_SECRET=replace-with-a-long-random-secret
```

Optional settings include `QDRANT_COLLECTION`, `EMBED_MODEL`, `EMBED_DIM`, `RERANK_MODEL`,
`LLM_MODEL`, `ROUTER_MODEL`, `DATA_DIR`, `UPLOAD_DIR`, `REPO_DIR`, `GUARDRAILS_PATH`,
`CACHE_ENABLED`, and `REDIS_URL`. See `app/config.py` for defaults.

Start PostgreSQL and Qdrant, apply the schema, and run the API:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. The application creates the configured Qdrant collection
at startup when needed.

## API

Use the JWT returned by `/signin` as `Authorization: Bearer <token>`. Document upload, processing,
and deletion require an admin token.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/register` | Create a user; only the `admin` role is elevated. |
| `POST` | `/signin` | Authenticate and return a JWT. |
| `GET` | `/me` | Return the current user. |
| `POST` | `/upload` | Upload and immediately ingest one PDF. |
| `POST` | `/process` | Ingest PDFs from `REPO_DIR`; skip known hashes and refresh guardrails/evals. |
| `GET` | `/` | List ingested documents. |
| `DELETE` | `/{doc_id}` | Delete document metadata, vectors, and uploaded file. |
| `POST` | `/chat` | Route an authenticated question through the multimodal RAG graph. |

Example chat request:

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{"question": "What does the document say about ...?"}
```

Only PDF files are accepted by `/upload`. Repository PDFs belong in `data/repo`; uploads default to
`data/uploads`.

## Guardrails and evaluations

NeMo's `self_check_input` rail in `app/guardrails/config` blocks questions outside the configured
document topics. If NeMo is unavailable, the same allow/block decision is made by an OpenAI topic
classifier. Generated answering rules are stored in `data/guardrails.json` and included in the RAG
answer prompt. Document processing refreshes `prompts.yml`, rules, and `evals/golden_dataset.json`.

Run the evaluation suite with the API's `.env` and services available:

```powershell
python -m evals.run_evals
```

It reports routing accuracy for allowed/blocked cases and keyword recall for document-derived RAG
answers. RAG checks may be skipped on provider or rate-limit errors while routing is still reported.

## Database migrations

Revisions are in `migrations/versions`; the initial revision creates `users` and `documents` plus
their indexes. The Alembic environment reads `DATABASE_URL` and the SQLAlchemy metadata from the
application.

```powershell
alembic current
alembic history
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic downgrade -1
```

Review autogenerated revisions before applying them.

## Project layout

```text
app/                 API, settings, models, auth, RAG graph, ingestion, and guardrails
data/                PDFs, uploads, generated guardrails, and local repository files
evals/               Golden dataset and evaluation runner
migrations/          Alembic environment and schema revisions
```

Troubleshooting: use `/health` and `/docs`; verify `DATABASE_URL`, `SYNC_DATABASE_URL`,
`QDRANT_URL`, provider keys, and that PostgreSQL/Qdrant are running. There is currently no dedicated
test suite or test command in the repository.
