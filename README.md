# Local LLM-Powered Agentic Quotation Platform

A self-hosted conversational quotation platform powered by local LLMs. It combines an Ollama-based chat agent, Qdrant vector search, a FastAPI backend, a React frontend, and an MCP service for quotation operations.

The platform is domain-flexible: the current seed data and workflow demonstrate interior quotations, but the architecture can support other product, service, or project quotation workflows.

## Architecture

The complete application runs as one Docker Compose stack:

| Service | Responsibility | Local port |
| --- | --- | ---: |
| `frontend` | Vite/React chat interface; restores sessions and displays quotation PDFs | `3000` |
| `backend` | FastAPI API, LangGraph orchestration, conversation memory, intent and slot extraction, RAG search | `8000` |
| `quotation-mcp` | FastMCP tools for saving quotations and leads, generating PDFs, sending email, and scheduling consultations | `9000` |
| `ollama` | Local chat and embedding models through LangChain Ollama integrations | `11434` |
| `qdrant` | Vector database for semantic retrieval of pricing or catalog data | `6333` |
| `postgres` | LangGraph checkpoints and relational quotation, lead, and consultation data | `5432` |

### Request flow

1. The React client sends a message and `session_id` to the FastAPI `/chat` endpoint.
2. The LangGraph agent classifies intent, extracts missing details, searches Qdrant, and calculates a quotation.
3. The agent calls the quotation MCP server when a quotation or follow-up operation is needed.
4. The MCP server persists business records in Postgres and can generate a PDF served from its own HTTP endpoint.
5. The backend returns the response and current conversation state to the frontend.

The graph follows this path for quotation requests:

```text
intent_agent -> slot_extractor -> intake_agent -> rag_search
    -> quote_agent -> mcp_tool_node -> responder
```

Non-quotation messages can take the `faq_responder` shortcut.

## Technology

- **Local LLMs:** Ollama, with `qwen2.5:7b` as the example chat model and `nomic-embed-text` for embeddings
- **Agent orchestration:** LangGraph and LangChain
- **API:** FastAPI and Uvicorn
- **Vector retrieval:** Qdrant with `QdrantVectorStore`
- **Persistence:** PostgreSQL with SQLAlchemy and LangGraph's Postgres checkpointer
- **Tool integration:** Model Context Protocol with the official `mcp` SDK and FastMCP
- **Frontend:** React 18 and Vite
- **Documents:** ReportLab-generated quotation PDFs

## Requirements

- Docker Desktop with Docker Compose
- At least one Ollama chat model and the embedding model downloaded locally through the Ollama container
- `curl` or another HTTP client for API checks

## Setup

1. Create the environment file expected by the backend:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell, use `Copy-Item .env.example .env`.

2. Start the supporting infrastructure:

   ```bash
   docker compose up -d ollama qdrant postgres
   ```

3. Download the example Ollama models:

   ```bash
   docker exec -it interior-ollama ollama pull nomic-embed-text
   docker exec -it interior-ollama ollama pull qwen2.5:7b
   ```

4. Seed Qdrant with the sample pricing data:

   ```bash
   docker compose run --rm backend python -m app.rag.seed_qdrant
   ```

5. Build and start the full platform:

   ```bash
   docker compose up -d --build
   ```

Open the application at **http://localhost:3000**. The Qdrant dashboard is available at **http://localhost:6333/dashboard**.

## Try the API

Send multiple messages with the same `session_id` so the agent can retain the conversation:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo-1","message":"I need a quotation for a 3BHK apartment."}'
```

Available backend endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/chat` | Process one conversational turn |
| `GET` | `/session/{session_id}` | Restore messages, slots, intent, and quote total |
| `GET` | `/quotation/{quotation_id}` | Read quotation details and PDF URL |
| `GET` | `/health` | Check API availability |

The MCP endpoint is available at `http://localhost:9000/mcp`.

## Repository layout

```text
.
├── backend/                    # FastAPI API and LangGraph agent
│   └── app/
│       ├── graph/              # State, nodes, routing, and schemas
│       ├── llm/                # LangChain Ollama client
│       ├── mcp/                # MCP client used by the graph
│       ├── rag/                # Embeddings, Qdrant, and seed script
│       └── db/                 # Read models and async database session
├── frontend/                   # React/Vite conversational UI
│   └── src/
│       ├── components/         # Chat window and message bubbles
│       ├── api.js              # Backend request wrapper
│       └── App.jsx             # Session and chat state
├── quotation-mcp-server/       # FastMCP quotation and document tools
│   ├── db/                     # Lead, quotation, and consultation models
│   ├── services/               # PDF and email services
│   └── server.py               # MCP tools and PDF route
├── data/pricing_seed.json       # Example retrieval data
└── docker-compose.yml           # Complete service topology
```

## MCP tools

The quotation MCP server exposes these tools:

- `create_quotation` stores a quotation and returns its ID.
- `generate_pdf` creates a quotation PDF and returns a fetchable URL.
- `send_email` sends the PDF when SMTP is configured, or logs a local simulation.
- `save_lead` upserts a lead by phone number.
- `schedule_design_consultation` creates or finds a lead and books a consultation slot.

The base conversation flow currently creates quotations and generates PDFs. Lead capture is not yet wired into the default intake flow, so the email and consultation tools are available through MCP but are not automatically invoked by every conversation.

## Development

Run the backend locally from `backend/`:

```bash
uvicorn app.main:app --reload
```

Run the frontend locally from `frontend/`:

```bash
npm install
npm run dev
```

For a production frontend build:

```bash
npm run build
```

Configure service URLs and model names in `.env`; Docker Compose uses the internal service names, while browser-facing URLs use `localhost` ports.
