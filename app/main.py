from fastapi import FastAPI


from .routers import auth, documents, chat

    
app = FastAPI(title="RAG API", version="1.0.0")

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)

@app.get("/health", tags=["health"])
def health():
    return {"status": "OK", "message":"This is my new deployment"}
