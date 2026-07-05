from ..config import get_settings
settings = get_settings()

import cohere
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models
from langchain_openai import ChatOpenAI

def cohere_client() -> cohere.AsyncClientV2:
    return cohere.AsyncClientV2(api_key=settings.cohere_api_key)

def qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


def openai_client(model_name = "gpt-4.1") -> ChatOpenAI:
    return ChatOpenAI(api_key=settings.openai_api_key, model=model_name)


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
                                            distance=models.Distance.COSINE,
                                            hnsw_config=models.HnswConfigDiff(m = 16, ef_construct=100)
                                        )
                                    },
                                    sparse_vectors_config={
                                            "bm25":models.SparseVectorParams(modifier=models.Modifier.IDF)
                                    }
                                )
    
    print("INFO: ", "Collection is Ready....")
    
    