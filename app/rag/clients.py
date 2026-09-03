from openai import AsyncOpenAI

from ..config import get_settings
settings = get_settings()

import cohere
from qdrant_client import AsyncQdrantClient, models
from langchain_openai import ChatOpenAI
from langchain_core.rate_limiters import InMemoryRateLimiter

_extract_limiter = InMemoryRateLimiter(requests_per_second=0.4, check_every_n_seconds=0.2, max_bucket_size=2)

def openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)

def cohere_client() -> cohere.AsyncClientV2:
    return cohere.AsyncClientV2(api_key=settings.cohere_api_key)

def qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)

# planner / grading / summaries
def openai_client_planner(model_name = "gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(api_key=settings.openai_api_key, model=model_name, temperature=0, max_retries=12)

# vision extraction (throttled)
def openai_client_vision(model_name="gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(api_key=settings.openai_api_key, model=model_name, temperature=0, max_retries=12, rate_limiter=_extract_limiter)

# final answers + vision QA
def openai_client_final(model_name="gpt-4o") -> ChatOpenAI:
    return ChatOpenAI(api_key=settings.openai_api_key, model=model_name, temperature=0, max_retries=12)
  

async def ensure_collection() -> None:
    ### 
    qdr = qdrant_client()
    COLLECTION = settings.qdrant_collection
    
    if await qdr.collection_exists(COLLECTION):
        print("Collection exist")
        return None
    
    await qdr.create_collection(COLLECTION, 
                                    vectors_config={
                                        "dense":models.VectorParams(
                                            size=settings.embed_dim,
                                            distance=models.Distance.COSINE
                                        )
                                    },
                                    sparse_vectors_config={
                                            "bm25":models.SparseVectorParams(modifier=models.Modifier.IDF)
                                    }
                                )
    for f in ("doc", "kind"):
        await qdr.create_payload_index(COLLECTION, f, models.PayloadSchemaType.KEYWORD)
    await qdr.create_payload_index(COLLECTION, "page", models.PayloadSchemaType.INTEGER)
    await qdr.create_payload_index(COLLECTION, "list_id", models.PayloadSchemaType.INTEGER)
    await qdr.create_payload_index(COLLECTION, "item_no", models.PayloadSchemaType.INTEGER)
    
    print("INFO: ", "Collection is Ready....")

