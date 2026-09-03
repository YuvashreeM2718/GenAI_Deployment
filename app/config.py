from functools import lru_cache
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- API keys ---
    cohere_api_key: str = ""
    openai_api_key: str = ""

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "multimodel_rag"

    # --- Models ---
    embed_model: str = "embed-v4.0"        # Cohere multimodal embeddings (text + image)
    embed_dim: int = 1024
    rerank_model: str = "rerank-v3.5"      # Cohere cross-encoder reranker
    llm_model: str = "gpt-4o"              # vision-capable, so it can explain figures
    router_model: str = "gpt-4o-mini"      # cheap model just for routing/classification

    # --- Auth (JWT) ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # --- Storage ---
    data_dir: str = "data"
    upload_dir: str = "data/uploads"       # user files uploaded via /upload
    repo_dir: str = "data/repo"            # pre-existing folder scanned by /process
    guardrails_path: str = "data/guardrails.json"
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    sync_database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"

    # --- RAG tuning ---
    dpi: int = 150                         # page render resolution for the answer LLM (high quality)
    image_embed_dpi: int = 100             # lower-res render used ONLY for embedding -> smaller Cohere payload
    ingest_batch: int = 16                 # pages buffered per batch (memory ceiling)
    image_embed_batch: int = 4             # images per Cohere embed call (small = robust for large/complex pages)
    candidate_k: int = 30                  # hybrid candidates before reranking
    top_k: int = 8                         # reranked hits kept
    max_context_images: int = 4            # cap page images sent to the LLM
    max_batch : int = 8000                 # max characters any single LLM call sees
    
    NS: str = "179c61d7-a347-42db-afa8-3709fb25f3ee"

    # --- RAG cache (Redis) ---
    cache_enabled: bool = False
    cache_ttl_seconds: int = 60 * 60 * 24     # how long a cached answer stays valid
    cache_similarity: float = 0.85            # cosine >= this -> treat as "same question"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Export keys so libraries that read os.environ directly (langchain_openai's ChatOpenAI,
    # NeMo Guardrails, etc.) can find them — pydantic only loads .env into THIS object.
    if s.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", s.openai_api_key)
    if s.cohere_api_key:
        os.environ.setdefault("COHERE_API_KEY", s.cohere_api_key)
    return s

