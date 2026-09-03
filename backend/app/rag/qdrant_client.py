"""
Qdrant access via LangChain's QdrantVectorStore.
Replaces the old raw qdrant-client calls -- LangChain handles embedding +
upsert + similarity search together, we just supply Documents and filters.
"""

from functools import lru_cache

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams

from app.config import settings
from app.rag.embeddings import get_embedding_model


@lru_cache(maxsize=1)
def get_vectorstore() -> QdrantVectorStore:
    """Cached vector store -- creates the collection on first use if missing."""
    client = QdrantClient(url=settings.qdrant_url)

    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=settings.embed_dim, distance=Distance.COSINE),
        )

    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=get_embedding_model(),
    )


def upsert_pricing_items(items: list[dict]) -> int:
    """
    Embed and upsert a list of pricing items.
    Each item must have: category, property_type, city, style, price, unit.
    Returns the number of documents upserted.
    """
    vectorstore = get_vectorstore()
    print('vectorstore',vectorstore)

    documents = [
        Document(
            page_content=(
                f"{item['category']} {item['style']} {item['city']} "
                f"{item['property_type']} interior design cost"
            ),
            metadata=item,
        )
        for item in items
    ]

    print('documents',documents)

    ids = vectorstore.add_documents(documents)
    return len(ids)


def search_pricing(
    query: str,
    city: str | None = None,
    style: str | None = None,
    top_k: int = 8,
) -> list[dict]:
    """
    Retrieve top-k pricing line items relevant to the query text,
    optionally filtered by city and/or style (matched against metadata).
    """
    vectorstore = get_vectorstore()
    print('vectorstore',vectorstore)

    conditions = []
    if city:
        conditions.append(FieldCondition(key="metadata.city", match=MatchValue(value=city)))
    if style:
        conditions.append(FieldCondition(key="metadata.style", match=MatchValue(value=style.lower())))
    qdrant_filter = Filter(must=conditions) if conditions else None

    print('qdrant_filter',qdrant_filter)

    results = vectorstore.similarity_search(query, k=top_k, filter=qdrant_filter)
    print("results",results)
    return [doc.metadata for doc in results]
