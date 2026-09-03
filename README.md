# MultiModel RAG Application

MultiModel RAG Application is a FastAPI backend for authenticated, multimodal retrieval-augmented generation (RAG). It ingests PDF documents, stores searchable vectors in Qdrant, and answers questions through a LangGraph agent workflow. OpenAI provides the language and vision models; Cohere provides embeddings and reranking.

## Features

- JWT authentication with user and admin roles
- PDF upload and batch processing from a repository folder
- Text and page-image ingestion for multimodal retrieval
- Hybrid dense and sparse search in Qdrant
- Cohere reranking before answer generation
- LangGraph-based chat orchestration
- Optional Redis answer cache
- NeMo Guardrails configuration and automatic guardrail refresh after ingestion
- FastAPI Swagger UI at `/docs`

## Architecture

```text
Client
  |
  v
FastAPI routers
  |-- Auth and JWT security
  |-- Document upload/process/delete
  `-- Chat
        |
        v
    LangGraph agent
        |-- OpenAI planner and answer model
        |-- Cohere embeddings and reranker
        |-- Qdrant hybrid retrieval
        `-- Optional Redis cache

PostgreSQL stores users and document metadata.
Qdrant stores document vectors and retrieval payloads.
```

## Multimodal RAG query services

The `/chat` endpoint sends each question through a LangGraph workflow. A planner first identifies the information needs, selects the best service for each need, and splits unrelated requests into sub-questions. The selected services can run in parallel. Their answers are combined, checked for grounding and completeness, and cached when accepted.

```text
Question
  -> NeMo input guardrail
  -> planner and document-aware routing
  -> semantic cache lookup
  -> one or more RAG services
  -> combine sub-answers
  -> self-check: grounded and useful?
       |-- no: retrieve again with a corrective lookup question (up to 2 retries)
       `-- yes: store answer in the optional cache and return it
```

The planner uses these routing rules:

- `list_all`: enumerate EVERY entry of a numbered or itemized list in the documents, such as references, bibliography entries, glossary terms, or clauses.
- `summarize`: summarize a whole document or specific pages.
- `visual`: answer questions about charts, scanned pages, photos, diagrams, or what a figure shows.
- `lookup`: handle everything else, including specific facts, terms, explanations, and best-effort numeric questions.

### `lookup` service

The default service performs hybrid retrieval in Qdrant. It combines dense Cohere embeddings with sparse BM25 search using reciprocal rank fusion, then applies Cohere reranking. An OpenAI planner grades the retrieved chunks for relevance. If no useful chunks remain, the service rewrites the query with more specific keywords and retries retrieval.

The selected chunks are expanded to their complete source pages, up to the configured context limit, before the final OpenAI model answers. The answer prompt requires the model to use only the retrieved context, avoid invented numbers, and say when the answer is not present.

### `list_all` service

This service is designed for completeness rather than only top-ranked snippets:

1. It searches for list items or pages containing lists.
2. It identifies the relevant document and `list_id` values.
3. It scrolls Qdrant until every item in the selected list has been collected.
4. It sorts entries by `item_no` and asks the model to format every relevant entry without dropping items.

It examines at most the two highest-ranked candidate lists. If no list is found, or the extracted list is not relevant, it falls back to `lookup`.

### `summarize` service

The summarizer loads the requested document or pages and keeps documents separated. For large documents, page text is packed into bounded batches. Independent batches are summarized in parallel, then summarized again in progressively smaller levels until the final context fits the configured `MAX_BATCH` size. Page references are preserved so the final answer can identify its source pages.

### `visual` service

The visual service searches Qdrant specifically for image payloads, such as rendered PDF pages, and selects the top visual matches. It sends the page images and document/page labels to the vision-capable OpenAI model so it can interpret charts, diagrams, photos, and scanned content. If no image result is available, it falls back to `lookup`.

### Multi-intent questions

The planner can create multiple service calls when a question contains separate needs. For example:

```text
What does the chart show and summarize page 3?
```

This becomes one `visual` sub-question and one `summarize` sub-question. The graph runs both branches, combines their answers into one response, and verifies that every part of the original question was addressed.

## Requirements

- Python 3.11 or newer
- PostgreSQL 14 or newer
- Qdrant running locally or remotely
- An OpenAI API key
- A Cohere API key
- Redis only if `CACHE_ENABLED=true`

The default local service URLs are:

| Service | URL | Default credentials/database |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | `rag` / `rag`, database `rag` |
| Qdrant | `http://localhost:6333` | No authentication |
| Redis | `localhost:6379` | Database `0` |

Update the connection settings if your local services use different values.

## Installation

From the project root, create and activate a virtual environment in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the project root. At minimum, set the provider keys and database connection:

```dotenv
OPENAI_API_KEY=your-openai-api-key
COHERE_API_KEY=your-cohere-api-key

DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
SYNC_DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
QDRANT_URL=http://localhost:6333

# Change this outside local development.
JWT_SECRET=replace-with-a-long-random-secret
```

Pydantic settings are case-insensitive, so the uppercase names above map to the fields in `app/config.py`.

Optional settings include:

```dotenv
QDRANT_COLLECTION=multimodel_rag
EMBED_MODEL=embed-v4.0
EMBED_DIM=1024
RERANK_MODEL=rerank-v3.5
LLM_MODEL=gpt-4o
ROUTER_MODEL=gpt-4o-mini
DATA_DIR=data
UPLOAD_DIR=data/uploads
REPO_DIR=data/repo
GUARDRAILS_PATH=data/guardrails.json
CACHE_ENABLED=false
REDIS_URL=redis://localhost:6379/0
```

## Database and API startup

1. Make sure PostgreSQL and Qdrant are running.
2. Apply the PostgreSQL migrations:

   ```powershell
  alembic upgrade head
   ```

3. Start the API:

   ```powershell
   uvicorn app.main:app --reload
   ```

The API is available at `http://127.0.0.1:8000`.

Useful URLs:

- Health check: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

When the application starts, it creates the configured Qdrant collection if it does not already exist. PostgreSQL schema changes are managed with Alembic. Run `alembic upgrade head` after installing dependencies and whenever new migrations are added.

## API workflow

All protected endpoints expect the token returned by `/signin` in the HTTP header:

```text
Authorization: Bearer <access_token>
```

### Register

```http
POST /register
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "change-this-password",
  "role": "admin"
}
```

The API accepts `admin` or `user`; any other role is stored as `user`.

### Sign in

```http
POST /signin
Content-Type: application/json

{
  "username": "admin@example.com",
  "password": "change-this-password"
}
```

The response contains an `access_token`.

### Process repository PDFs

Place PDFs in `data/repo` (or the configured `REPO_DIR`) and call:

```http
POST /process
Authorization: Bearer <admin-token>
```

Already-processed files are skipped by SHA-256 hash.

### Upload one PDF

```powershell
curl.exe -X POST http://127.0.0.1:8000/upload `
  -H "Authorization: Bearer <admin-token>" `
  -F "file=@data\pdf\example.pdf"
```

Only PDF files are accepted. Uploaded files are saved under `data/uploads` by default and ingested immediately.

### List and delete documents

```http
GET /
Authorization: Bearer <token>
```

The document list requires any authenticated user. Deletion requires an admin:

```http
DELETE /{doc_id}
Authorization: Bearer <admin-token>
```

### Ask a question

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "question": "What does the document say about ...?"
}
```

The response contains `answer` and a boolean `cached` flag.

## Project layout

```text
app/
  main.py                 FastAPI application and startup lifecycle
  config.py               Environment-backed settings
  db.py, models.py        SQLAlchemy database setup and models
  schemas.py              Request and response models
  security.py             Password hashing and JWT authentication
  routers/                Auth, document, and chat endpoints
  rag/                    Ingestion, retrieval, clients, cache, and graphs
  guardrails/             Guardrail engine and rules
  agent/                  Per-request agent context
data/
  pdf/                    Local PDF resources
  repo/                   PDFs processed by `/process`
  uploads/                PDFs uploaded through `/upload`
migrations/               Alembic configuration and revisions
evals/                    Evaluation dataset and runner
```

## Troubleshooting

- `401 Unauthorized`: obtain a fresh token from `/signin` and send it as `Authorization: Bearer <token>`.
- `403 Admin access required`: use a user registered with the `admin` role for document management endpoints.
- Qdrant connection errors: verify `QDRANT_URL` and that the Qdrant service is reachable.
- PostgreSQL connection errors: verify both `DATABASE_URL` and `SYNC_DATABASE_URL`, then run `alembic upgrade head`.
- Ingestion failures: confirm the file is a readable PDF and that both OpenAI and Cohere keys are available.

## Development notes

The project currently has no dedicated test command or test suite in the repository. Use `/health`, `/docs`, and a complete register/sign-in/ingest/chat flow to smoke-test a local build.
