"""
LangChain-based embedding model, backed by Ollama.
Replaces the old raw-httpx call to /api/embeddings.
"""

from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from app.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> OllamaEmbeddings:
    """Cached embedding model -- one instance reused everywhere (RAG search + seeding)."""
    return OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )
