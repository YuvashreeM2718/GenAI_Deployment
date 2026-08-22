from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str

class LoginDTO(BaseModel):
    username: str
    password: str 

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    pages: int
    status: str
    created_at: datetime


class ProcessResponse(BaseModel):
    processed: list[str]
    skipped: list[str]


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
