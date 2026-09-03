"""
FastAPI app: compiles the LangGraph agent once at startup (with a Postgres
checkpointer for multi-turn memory) and exposes it via /chat, plus a couple
of read-only endpoints the frontend uses to restore history and fetch
quotation details.
"""

from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel

from app.config import settings
from app.db.models import Quotation
from app.db.session import AsyncSessionLocal
from app.graph.build_graph import build_graph_definition


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        await checkpointer.setup()
        graph_definition = build_graph_definition()
        app.state.graph = graph_definition.compile(checkpointer=checkpointer)
        yield


app = FastAPI(title="Interior Design Quotation Agent", lifespan=lifespan)

# Dev-friendly CORS so the React frontend (served from a different port) can call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    async def event_stream():
        config = {"configurable": {"thread_id": req.session_id}}

        async for mode, chunk in app.state.graph.astream(
            {
                "session_id": req.session_id,
                "messages": [HumanMessage(content=req.message)],
            },
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                message, metadata = chunk
                if (
                    metadata.get("langgraph_node") == "faq_responder"
                    and isinstance(message.content, str)
                    and message.content
                ):
                    yield (
                        "event: token\n"
                        f"data: {json.dumps({'content': message.content}, ensure_ascii=False)}\n\n"
                    )
            elif mode == "updates":
                for node_name, update in chunk.items():
                    if isinstance(update, dict) and isinstance(update.get("reply"), str):
                        yield (
                            "event: reply\n"
                            f"data: {json.dumps({'content': update['reply'], 'node': node_name}, ensure_ascii=False)}\n\n"
                        )

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/session/{session_id}")
async def get_session(session_id: str) -> dict:
    """
    Restore a conversation: full message history + current slots/intent,
    read straight from the LangGraph checkpoint for this thread_id.
    """
    graph = app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    snapshot = await graph.aget_state(config)
    values = snapshot.values or {}

    messages = [
        {"role": "user" if m.type == "human" else "assistant", "content": m.content}
        for m in values.get("messages", [])
    ]

    return {
        "session_id": session_id,
        "messages": messages,
        "slots": values.get("slots"),
        "intent": values.get("intent"),
        "quote_total": values.get("quote_total"),
    }


@app.get("/quotation/{quotation_id}")
async def get_quotation(quotation_id: str) -> dict:
    """Fetch a quotation's full details directly from Postgres (written by the MCP server)."""
    async with AsyncSessionLocal() as session:
        quotation = await session.get(Quotation, quotation_id)

    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")

    pdf_url = None
    if quotation.pdf_filename:
        pdf_url = f"{settings.mcp_public_base_url}/pdfs/{quotation.pdf_filename}"

    return {
        "quotation_id": quotation.id,
        "property_type": quotation.property_type,
        "location": quotation.location,
        "style": quotation.style,
        "budget": quotation.budget,
        "breakdown": quotation.breakdown,
        "total": quotation.total,
        "status": quotation.status,
        "pdf_url": pdf_url,
        "created_at": quotation.created_at.isoformat(),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
