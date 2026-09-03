"""
Central configuration for the backend.
All values are read from environment variables (see .env.example).
Keep this file dumb: just settings, no logic.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "interior_pricing"
    embed_dim: int = 768

    # Postgres -- plain DSN, used by LangGraph's AsyncPostgresSaver checkpointer
    database_url: str = ""
    # Same DB, SQLAlchemy-flavored URL (async psycopg3 driver) for the read-only
    # quotation/lead query layer below
    sqlalchemy_database_url: str = ""

    # MCP
    mcp_server_url: str = ""
    # Browser-reachable base URL for the MCP server's PDF links (differs from the
    # internal docker network address above, since the browser isn't on that network)
    mcp_public_base_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
