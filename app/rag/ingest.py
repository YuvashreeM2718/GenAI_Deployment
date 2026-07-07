import asyncio, base64, gc, uuid, pymupdf, httpx
from qdrant_client import models
import cohere
from ..config import get_settings
from .clients import cohere_client, qdrant_client

settings = get_settings()
NS = uuid.UUID(settings.NS)

def chunk_id(doc_id:int, page:int) -> str:
    return uuid.uuid5(NS, f"{doc_id}:{page}")

def _is_visual(page:pymupdf.Page) -> bool:
    if not page.get_text().strip():
        return True
    
    for imageInfo in page.get_image_info():
        if imageInfo.get("width", 0) * imageInfo.get("hight", 0) > 200 * 200:
            return True
    
    try:    
        if page.find_tables().tables:
            return True
    except Exception:
        pass
    
    return False

def _page_data_url(page:pymupdf.Page) -> str:
    png = page.get_pixmap(dpi=settings.image_embed_dpi).tobytes("png")
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


async def _embed(co:cohere.AsyncClientV2, texts = None, images = None, input_type = "search_documents", max_retry: int = 3):        
    kwargs = {
        "model":settings.embed_model,
        "input_type":input_type,
        "embedding_types" : ["float"]
    }
    
    if texts is not None:
        kwargs["texts"] = texts
        
    if images is not None:
        kwargs["images"] = images
    
    last_error = None
    for attempt in range(max_retry):
        try:
            response = await co.embed(**kwargs)
            return [list(value) for value in response.embeddings.float_]
        except httpx.TransportError as error:
            last_error = error
            if attempt < max_retry:
                await asyncio.sleep(1.5 * attempt)
               
    raise last_error 
                
        

async def _embed_images(co:cohere.AsyncClientV2, allimages: list):

    out = {}
    for start in range(0, len(allimages), settings.image_embed_batch):
        chunk = allimages[start : (start + settings.image_embed_batch)]
        images = [d["data_url"] for d in chunk]                    
        vectors = await _embed(co, images=images)
        
        for index, vector in enumerate(vectors):
            c = chunk[index]
            out[c["id"]] = vector
            
    return out
            
        
async def process_pdf(user_id:int, doc_id: int, path: str, fileName: str) -> int:
    co = cohere_client()
    qdr = qdrant_client()
    
    docs = pymupdf.open(path)
    text_chunks = []
    image_chunks = []
    total = 0
    
    
    async def flush():
        if (len(text_chunks) + len(image_chunks)) == 0:
            return;
               
        text_embeddings = [] if len(text_chunks) == 0 else await _embed(co, texts=[c["text"] for c in text_chunks ])
        image_embeddings = {} if len(image_chunks) == 0 else await _embed_images(co, image_chunks)
        
        points = []
        for index, vector in enumerate(text_embeddings):
            chunk = text_chunks[index]        
            point = models.PointStruct(
                id = chunk["id"],
                vector= {
                    "dense": vector,
                    "bm25": models.Document(text=chunk["text"], model="Qdrant/bm25")
                },
                payload=chunk
            )        
            points.append(point)
            
            
        for index, chunk in enumerate(image_chunks):
            vector = image_embeddings[chunk["id"]]  
            chunk.pop("data_url") 
            point = models.PointStruct(
                id = chunk["id"],
                vector= {
                    "dense": vector
                },
                payload=chunk
            )        
            
            points.append(point)
            
        
        await qdr.upsert(settings.qdrant_collection, points=points)                

        points.clear()
        text_chunks.clear()
        image_chunks.clear()
        gc.collect()  
    
    for i in range(len(docs)):
        page = docs[i]
        isVisual = _is_visual(page)
        
        metadata = {
            "id": chunk_id(doc_id, i + 1),
            "user_id": user_id,
            "doc_id":doc_id,
            "source":fileName,
            "path":path,
            "page":i+1,
            "type": "image" if isVisual else "text",
            "text": "" if isVisual else page.get_text().strip()
        }
        
        if isVisual:
            metadata["data_url"] = _page_data_url(page)
        
        if isVisual:
            image_chunks.append(metadata)
        else:
            text_chunks.append(metadata)
        
        total += 1
        
        if total >= settings.ingest_batch:
            await flush()
            total = 0

    await flush()  
    return len(docs)

            
        
    
##### chunks = cohere - reate limit - 
    
        








#### per min call - max token = 

