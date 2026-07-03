from fastapi import APIRouter, Depends

from ..models import User
from ..schemas import ChatRequest, ChatResponse
from ..security import get_current_user

router = APIRouter(tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    return ChatResponse(answer="API Call is Done...", sources=["This is my source"])
