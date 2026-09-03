"""Semantic RAG cache backed by Redis.

Why: the full RAG pipeline (embed -> hybrid search -> rerank -> vision LLM) is slow and costly.
If a *similar* question was answered recently, we return that answer instantly.

How (simple version):
  * We embed the question (Cohere) and store {embedding, answer, sources} in Redis.
  * On a new question, we embed it and compare (cosine) against cached embeddings.
    If the best match >= cache_similarity, it's "the same question" -> return the cached answer.
"""
import json
import math

import redis.asyncio as redis

from ..config import get_settings
from app.rag.retrieve import _embed_query

settings = get_settings()
_INDEX = "ragcache:index"       # set of cache keys
_PREFIX = "ragcache:item:"

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def lookup(question: str):
    """Return (answer, sources) if a similar question is cached, else None."""
    if not settings.cache_enabled:
        return None
    r = _redis()
    try:
        keys = await r.smembers(_INDEX)
        if not keys:
            return None
        
        q_vec = await _embed_query(question)
        best, best_key = 0.0, None
        for key in keys:
            raw = await r.get(_PREFIX + key)
            if not raw:
                await r.srem(_INDEX, key)     # expired -> drop from index
                continue
            item = json.loads(raw)
            score = _cosine(q_vec, item["embedding"])
            if score > best:
                best, best_key = score, key
        if best_key and best >= settings.cache_similarity:
            item = json.loads(await r.get(_PREFIX + best_key))
            return item["answer"], item.get("sources", [])
        
    except Exception as exc:
        print(f"[cache] lookup skipped: {exc}")
    return None


async def store(question: str, answer: str, sources: list[str]) -> None:
    if not settings.cache_enabled:
        return
    
    r = _redis()
    try:
        q_vec = await _embed_query(question)
        key = str(abs(hash(question)))
        payload = json.dumps({"question": question, "embedding": q_vec, "answer": answer, "sources": sources})
        await r.set(_PREFIX + key, payload, ex=settings.cache_ttl_seconds)
        await r.sadd(_INDEX, key)
        print("prefix key",_PREFIX + key)
    except Exception as exc:
        print(f"[cache] store skipped: {exc}")
