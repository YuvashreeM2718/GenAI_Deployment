"""Chat endpoint: routes a question through the LangGraph multi-agent system, scoped to the logged-in user."""
from fastapi import APIRouter, Depends

from app.rag.graph.multinode_graph import run_chat

from ..models import User
from ..schemas import ChatRequest, ChatResponse
from ..security import get_current_user
from ..agent.context import set_current_user

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    set_current_user(user.id)                       
    result = await run_chat(req.question)
    return ChatResponse(
        answer = result["answer"],
        cached = result["cached"]
    )
