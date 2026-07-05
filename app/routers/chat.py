from fastapi import APIRouter, Depends

from ..models import User
from ..schemas import ChatRequest, ChatResponse
from ..security import get_current_user
from ..rag.retrieve import generate
router = APIRouter(tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    
    ### reter gener answer
    answer = await generate(req.question, user.id)
    
    return ChatResponse(answer=answer, sources=["This is my source"])
