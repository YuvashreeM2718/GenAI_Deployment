import pymupdf, base64
from qdrant_client import models

from app.rag.ingest import embed_texts, with_backoff
from ..config import get_settings
from .clients import cohere_client, qdrant_client


settings = get_settings()
qdr = qdrant_client()

async def _embed_query(query: str) -> list:
    co = cohere_client()
    r = await co.embed(model=settings.embed_model, input_type="search_query",
                       embedding_types=["float"], output_dimension=settings.embed_dim, texts=[query])
    return list(r.embeddings.float_[0])

async def hybrid_search(query, k=15, doc=None, kind=None):
    must = []
    if doc:  must.append(models.FieldCondition(key="doc",  match=models.MatchValue(value=doc)))
    if kind: must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
    not_manifest = [models.FieldCondition(key="kind", match=models.MatchValue(value="manifest"))]
    flt = models.Filter(must=must or None, must_not=not_manifest)

    qvec  = await embed_texts([query], input_type="search_query")
    qv = qvec[0]

    response = await qdr.query_points(settings.qdrant_collection,
        prefetch=[models.Prefetch(query=qv, using="dense", limit=25, filter=flt),
                  models.Prefetch(query=models.Document(text=query, model="Qdrant/bm25"),
                                  using="bm25", limit=25, filter=flt)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
    return [p.payload for p in response.points]

async def rerank(query, payloads, top_n=6):
    co = cohere_client()
    if len(payloads) <= top_n: return payloads
    
    r = await with_backoff(lambda: co.rerank(model="rerank-v3.5", query=query,
                     documents=[p["text"] for p in payloads], top_n=top_n))
    
    return [payloads[x.index] for x in r.results]

async def retrieve(query: str):
    """Full retrieval pipeline. Returns (context_points, primary_hit_ids)."""
    hits = await hybrid_search(query, settings.candidate_k)   # 1) hybrid recall
    hits = await rerank(query, hits, settings.top_k)          # 2) precision rerank
    primary = [h.id for h in hits]
    return hits, primary