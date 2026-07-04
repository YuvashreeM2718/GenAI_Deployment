from fastapi import FastAPI
from .rag.clients import ensure_collection

from .routers import auth, documents, chat

from contextlib import asynccontextmanager
@asynccontextmanager
async def create_vectordb(app:FastAPI):
    try:
        await ensure_collection()
    except Exception as error:
        print(F"Collection not created....")
    yield
    
app = FastAPI(title="RAG API", version="1.0.0", lifespan=create_vectordb)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
