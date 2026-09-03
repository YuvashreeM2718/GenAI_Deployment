from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime

# ---------------- Auth ----------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"          


class LoginDTO(BaseModel):
    username: str               # we log in with email
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: str
    created_at: datetime


class Token(BaseModel):
    access_token: str



# ---------------- Documents ----------------

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

# ---------------- Chat ----------------
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str                  
    # sources: list[str] = []
    cached: bool = False