from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- API keys ---
    cohere_api_key: str = ""
    openai_api_key: str = ""

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_documents"

    # --- Models ---
    embed_model: str = "embed-v4.0"        # Cohere multimodal embeddings (text + image)
    embed_dim: int = 1536
    rerank_model: str = "rerank-v3.5"      # Cohere cross-encoder reranker
    llm_model: str = "gpt-4o"              # vision-capable, so it can explain figures

    # --- Auth (JWT) ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # --- Storage ---
    data_dir: str = "data"
    upload_dir: str = "data/uploads"       # user files uploaded via /upload
    repo_dir: str = "data/repo"            # pre-existing folder scanned by /process
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"

    # --- RAG tuning ---
    dpi: int = 150                         # page render resolution for the answer LLM (high quality)
    image_embed_dpi: int = 100             # lower-res render used ONLY for embedding -> smaller Cohere payload
    ingest_batch: int = 16                 # pages buffered per batch (memory ceiling)
    image_embed_batch: int = 4             # images per Cohere embed call (small = robust for large/complex pages)
    candidate_k: int = 30                  # hybrid candidates before reranking
    top_k: int = 8                         # reranked hits kept
    max_context_images: int = 4            # cap page images sent to the LLM
    
    NS: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
