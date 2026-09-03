"""
LangChain-based Ollama chat client.
Replaces the old raw-httpx client: LangChain's ChatOllama handles the
request/response plumbing, and .with_structured_output() handles JSON
parsing + validation for us via Ollama's native JSON-schema mode.
"""

from functools import lru_cache

from langchain_ollama import ChatOllama
from pydantic import BaseModel

from app.config import settings

@lru_cache(maxsize=1)
def get_chat_model() -> ChatOllama:
    """Cached base chat model -- one instance reused across all nodes."""
    print("ollama model",settings.ollama_chat_model)
    return ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )


def get_structured_model(schema: BaseModel):
    """
    Chat model bound to a Pydantic schema. Calling .invoke(...) on the
    result returns a validated instance of `schema` instead of raw text.
    """
    return get_chat_model().with_structured_output(schema, method="json_schema")
