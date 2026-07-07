import pymupdf, base64
from qdrant_client import models
from ..config import get_settings
from .clients import cohere_client, qdrant_client, openai_client


settings = get_settings()


def _user_filer(user_id):
    return models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id)
                        )
                    ]
                )
    

async def embed_query(query):
    co = cohere_client()
    result = await co.embed(
            model=settings.embed_model,
            input_type="search_query",
            texts=[query],
            embedding_types=["float"]
        )
    return list(result.embeddings.float_)[0]


async def hybrid_search(user_id:int, query:str, k:int = 8):
    qrd = qdrant_client()
    points = await qrd.query_points(
        settings.qdrant_collection,
        prefetch=[
            models.Prefetch(
                query = await embed_query(query),
                using="dense", 
                limit=max(k*2, 40),
                filter=_user_filer(user_id),
            ),
             models.Prefetch(
                query = models.Document(text=query, model="Qdrant/bm25"),
                using="bm25", 
                limit=(2 * k),
                filter=_user_filer(user_id)
            )
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k
    )
    return points.points

async def reranker(query:str, points:list[models.PointStruct], k : int = 4):
    if not points:
        return points
    
    co = cohere_client()
    
    docs = []
    for p in points:
        if p.payload.get("text"):
            docs.append(p.payload.get("text"))
        else:
            docs.append(f"{p.payload.get("source")} p.{p.payload["page"]}")

       
    result = await co.rerank(model=settings.rerank_model, query=query, documents=docs, top_n=k)
    reOrder = [points[r.index] for r in result.results]
    return reOrder



async def retrieve(user_id: int, query: str):
    hybridPoints = await hybrid_search(user_id, query, settings.candidate_k)
    rerankeData = await reranker(query, hybridPoints, settings.top_k)  
    return rerankeData


def _doc_page_to_url(path:str, page:int) -> str:
    docs = pymupdf.open(path)
    page = docs[page - 1]
    png = page.get_pixmap(dpi=settings.image_embed_dpi).tobytes("png")
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


####### LLM Call and Generate the Answers........

SYSTEM_PROMPT = """
    You answer questions only the provided content from the user documents. 
    --- Context can contain images, charts and tables. look at the images and explain what they show.
    -- If the answer is not the context, say 'You could not find it.'
"""


def _build_message(query, contexts: list[models.PointStruct]):

    content = [
        {"type":"text", "text":f"Question: {query} \n --- CONTEXT ---- "}
    ]
    
    for context in contexts:
        if context.payload.get("type") == "image":
            content.append(
                {"type":"image_url", "image_url": 
                    {"url":_doc_page_to_url(context.payload.get("path"), context.payload.get("page") )}}
            )
        else:
            content.append(
                {"type":"text", "text":f"{context.payload.get("text")}"}
            )
        
    return content

async def generate(query:str, user_id:int):
    context = await retrieve(user_id, query)
    llm = openai_client()
    
    res = await llm.ainvoke([
        {"role":"system", "content":SYSTEM_PROMPT},
        {"role":"user", "content":_build_message(query, context)},
        ])
    
    return res.content
    
    
async def delete_document_vectors(doc_id:int):
    qrd = qdrant_client()
    await qrd.delete(settings.qdrant_collection, 
                     models.Filter(
                        must=[
                            models.FieldCondition(
                                key="doc_id",
                                match=models.MatchValue(value=doc_id)
                            )
                        ]
                    ) 
                )
    return True

    
    
    
    