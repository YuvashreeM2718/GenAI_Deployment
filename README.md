# RAG API — End-to-End Retrieval-Augmented Generation Service

A small, production-shaped **fully async** FastAPI service: users register, upload PDFs, and chat with them.
Retrieval is **multimodal hybrid RAG** (Cohere embeddings + Qdrant BM25, Cohere rerank, neighbour-page
expansion) with a vision LLM that can also explain figures. Files are **de-duplicated** — uploading the same
PDF twice skips re-processing and is ready for Q&A immediately.

Everything is async end to end: async SQLAlchemy 2.0 (asyncpg) + async Alembic, async endpoints, and async
Cohere / Qdrant / OpenAI clients.

## Architecture

```
app/
  main.py            FastAPI app + startup (ensure Qdrant collection)
  config.py          all settings (env-overridable)
  db.py              async PostgreSQL engine (asyncpg) + async session (SQLAlchemy 2.0)
  models.py          User, Document tables (SQLAlchemy 2.0 declarative)
  schemas.py         request/response models
  security.py        bcrypt password hashing, JWT, get_current_user
migrations/          Alembic (env.py + versions/) — database schema management
  routers/
    auth.py          /register  /signin  /me
    documents.py     /process  /upload  /read  /delete/{id}
    chat.py          /chat
  rag/
    clients.py       lazy Cohere / Qdrant / OpenAI clients + collection setup
    ingest.py        PDF -> route text/image -> Cohere embed -> Qdrant (dense + BM25)
    retrieve.py      hybrid search -> rerank -> neighbour expansion (per-user)
    generate.py      multimodal answer (gpt-4o), cites sources, explains figures
```

**Data flow:** metadata (users, documents) lives in **PostgreSQL** (schema managed by **Alembic**); vectors
live in **Qdrant**. Every vector carries a `user_id` so retrieval is isolated per user, and a `doc_id` so a
document can be deleted cleanly.

## Setup

```bash
cd rag_api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Postgres + Qdrant (Docker)
docker run -d -p 5432:5432 -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag postgres:16
docker run -d -p 6333:6333 qdrant/qdrant           # Qdrant >= v1.15.2 (builds BM25 vectors)

# 2) Config
cp .env.example .env                                # fill in COHERE_API_KEY, OPENAI_API_KEY, JWT_SECRET, DATABASE_URL

# 3) Create the database schema (Alembic)
alembic upgrade head

# 4) Run
bash run.sh                                         # open http://localhost:8000/docs
```

**Database migrations (Alembic):** the schema is defined by the SQLAlchemy models and versioned in
`migrations/versions/`. Apply them with `alembic upgrade head`. After changing a model, generate a new
migration with `alembic revision --autogenerate -m "describe change"` then `alembic upgrade head`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/register` | – | create a user |
| POST | `/signin` | – | get a JWT (send email as `username`) |
| GET | `/me` | ✅ | current user |
| POST | `/upload` | ✅ | upload one PDF (skips if already processed) |
| POST | `/process` | ✅ | process every PDF in `data/repo/` (skips duplicates) |
| GET | `/read` | ✅ | list your documents |
| DELETE | `/delete/{doc_id}` | ✅ | delete a document + its vectors |
| POST | `/chat` | ✅ | ask a question over your documents |

Authenticate in Swagger with the **Authorize** button (email + password), or send
`Authorization: Bearer <token>` from `/signin`.

## Quick try (curl)

```bash
curl -X POST localhost:8000/register -H 'content-type: application/json' \
     -d '{"email":"a@b.com","password":"secret"}'
TOKEN=$(curl -s -X POST localhost:8000/signin -d 'username=a@b.com&password=secret' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -X POST localhost:8000/upload -H "Authorization: Bearer $TOKEN" -F 'file=@mydoc.pdf'
curl -X POST localhost:8000/chat  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"question":"summarise the document"}'
```

## Notes
- **Processing is synchronous** (the request waits while the PDF is embedded). For large corpora, move
  ingestion to a background worker (FastAPI `BackgroundTasks` or a queue) — the ingest function is already
  isolated for that.
- **De-dup** is by SHA-256 of the file bytes, per user.
- Swap the generation model in `config.py` (`llm_model`); Cohere handles embeddings + reranking.
