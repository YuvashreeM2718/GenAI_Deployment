import time
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from ..config import get_settings
settings = get_settings()

import base64
import hashlib
from pathlib import Path
import fitz
from pydantic import BaseModel, Field
import pymupdf4llm
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from qdrant_client import AsyncQdrantClient, models

from app.rag.clients import cohere_client, openai_client_vision, qdrant_client

qdr = qdrant_client()
COLLECTION = settings.qdrant_collection
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class VisionPage(BaseModel):
    extracted_text: str = Field(description="ALL text visible on the page, transcribed verbatim; "
                                            "tabular content as one line per row; '' if none")
    caption: str = Field(description="detailed description of charts/photos/diagrams/layout; '' if none")

xllm = openai_client_vision()
vision_reader = xllm.with_structured_output(VisionPage)

def read_image_page(page):
    native = page.get_text().strip()
    aid = (f"\nThe page's raw text layer follows — copy exact values from it, use the image only "
           f"for structure and visuals:\n<text>\n{native[:6000]}\n</text>" if native
           else "\n(No text layer — transcribe carefully from the image.)")
    
    return vision_reader.invoke([HumanMessage(content=[
        {"type": "text", "text":
            "Read this document page. Return (1) extracted_text: every piece of text on the page, "
            "verbatim. Prefix every LIST-ITEM line with '- ' (markdown style), keeping its original "
            "number or letter (e.g. '- [3] ...' or '- 2. ...'). "
            "Tabular content as one line per row; (2) caption: a detailed description of "
            "any chart, photo, diagram or notable layout." + aid},
        {"type": "image_url", "image_url": {"url": page_data_url(page), "detail": "high"}}])])


def profile_page(page) -> str:
    """'image' | 'text'."""
    text_ = page.get_text().strip()
    if len(text_) < 200:                                       # scanned / picture page
        return "image"
    for it in page.get_image_info(xrefs=True):                 # big content image on a text page
        if it.get("width", 0) * it.get("height", 0) >= 200 * 200 and abs(fitz.Rect(it["bbox"])) / abs(page.rect) > 0.15:
            return "image"
    return "text"

def page_data_url(page, zoom=2.0):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()

def with_backoff(fn, tries=6):
    for a in range(tries):
        try:
            return fn()
        except Exception as e:
            print(e)
            if a == tries - 1 or ("429" not in str(e) and "rate" not in str(e).lower()):
                raise
            wait = min(2 ** a, 30)
            print(f"  rate-limited, retrying in {wait}s")
            time.sleep(wait)

async def embed_texts(texts, input_type="search_document"):
    co = cohere_client()
    out = []

    for i in range(0, len(texts), 90):
        batch = texts[i:i+90]
        r = await with_backoff(lambda: co.embed(model=settings.embed_model, input_type=input_type,
                embedding_types=["float"], output_dimension=settings.embed_dim, texts=batch))
        out += [list(v) for v in r.embeddings.float_]
    return out

async def embed_image(data_url):
    co = cohere_client()
    r = await with_backoff(lambda: co.embed(model=settings.embed_model, input_type="search_document",
            embedding_types=["float"], output_dimension=settings.embed_dim, images=[data_url]))
    return list(r.embeddings.float_[0])

def item_number(entry):
    e = entry.strip()
    if e.startswith("[") and "]" in e[:7] and e[1:e.index("]")].isdigit():
        return int(e[1:e.index("]")])
    
    "Hello".split(" ", )
    
    first = e.split(" ", 1)[0]                     # look at the first word only
    if first[:-1].isdigit() and first[-1] == ".":                  # "12."
        return int(first[:-1])
    
    if len(first) == 2 and first[0].isalpha() and first[1] in ".)": # "A." or "a)"
        return ord(first[0].upper()) - 64
    
    return None

def is_item(line):
    """A line is a list item if it starts with a markdown bullet OR with a number/letter marker."""
    return line.startswith(("- ", "* ")) or item_number(line) is not None

def split_page(lines):
    """ONE simple rule for every line: list item -> its own block, anything else -> text block."""
    blocks = []
    
    for line in lines:
        s = line.strip()
        if not s:
            continue
        
        if is_item(s):
            text = s[2:].strip() if s[:2] in ("- ", "* ") else s   # drop the bullet prefix
            blocks.append({"type": "item", "text": text})
        elif blocks and blocks[-1]["type"] == "text":
            blocks[-1]["text"] += "\n" + s                         # grow the current text block
        else:
            blocks.append({"type": "text", "text": s})
    return blocks

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

async def forget(doc):
    """One filter removes everything about a document — content AND its manifest point."""

    await qdr.delete(COLLECTION, 
               points_selector=models.FilterSelector(filter=models.Filter(must=[
                   models.FieldCondition(
                       key="doc", 
                       match=models.MatchValue(value=doc)
                       )
                   ])))

# --- the manifest lives in the SAME collection as special points ---
async def get_hash(doc):
    pts, _ = await qdr.scroll(COLLECTION, scroll_filter=models.Filter(must=[
        models.FieldCondition(key="kind", match=models.MatchValue(value="manifest")),
        models.FieldCondition(key="doc",  match=models.MatchValue(value=doc))]),
        limit=1, with_payload=True)
    return pts[0].payload["hash"] if pts else None

async def set_hash(doc_id, doc, h):
    await qdr.upsert(COLLECTION, points=[models.PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, doc)),          # deterministic id -> upsert replaces
        vector={"dense": [0.0] * settings.embed_dim},
        payload={"id":doc_id, "doc": doc, "kind": "manifest", "hash": h})])

def point(vec, payload):
    return models.PointStruct(id=str(uuid.uuid4()),
        vector={"dense": vec, "bm25": models.Document(text=payload.get("text", " "), model="Qdrant/bm25")},
        payload=payload)

def to_units(text_):
    return [text_] if len(text_) <= 1800 else splitter.split_text(text_)

# --- page text is reconstructed FROM the content points (payloads carry doc/page/seq/text) ---
async def load_pages(doc=None, pages=None):
    """[(doc, page, full_text)] in reading order, assembled from chunk/item payloads."""
    must = [models.FieldCondition(key="kind", match=models.MatchAny(any=["chunk", "item"]))]
   
    if doc:   must.append(models.FieldCondition(key="doc",  match=models.MatchValue(value=doc)))
    if pages: must.append(models.FieldCondition(key="page", match=models.MatchAny(any=list(pages))))
    frags, offset = [], None
    
    while True:
        pts, offset = await qdr.scroll(COLLECTION, scroll_filter=models.Filter(must=must),
                                 limit=200, offset=offset, with_payload=True)
        frags += [p.payload for p in pts]
        if offset is None: break
    by = {}
    for f in frags:
        by.setdefault((f["doc"], f["page"]), []).append(f)
        
    return [(d, pg, "\n".join(x["text"] for x in sorted(fr, key=lambda x: x.get("seq", 0))))
            for (d, pg), fr in sorted(by.items())]

async def page_text(doc, page):
    rows = await load_pages(doc, [page])
    return rows[0][2] if rows else ""

async def ingest(doc_id : int, pdf_path: str, filename: str) -> int:
    doc, h = Path(pdf_path).name, file_hash(pdf_path)
    if await get_hash(doc) == h:
        print(f"{doc}: unchanged, skipped"); return            # never process the same file twice
    await forget(doc)

    pdf   = fitz.open(pdf_path)
    stats = {"text": 0, "image": 0, "items": 0}
    list_id = 0
    last_no = None  
    total = 0                                           # which list are we in? (per document)
    
    for page_no, page in enumerate(pdf, 1):
        print("page & Page no", page, page_no)
        kind = profile_page(page)
        stats[kind] += 1
        pts = []

        # STEP 1 - get the page as LINES (both kinds end up in the same markdown-ish format)
        if kind == "image":
            vp = read_image_page(page)                         # vision: text (with '- ' bullets) + caption
            page_text_ = (vp.extracted_text.strip() +
                          (f"\n[VISUAL] {vp.caption.strip()}" if vp.caption.strip() else "")).strip()

            url = page_data_url(page)                          # rendered once, only for the embedding

            pts.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector={"dense": await embed_image(url),
                        "bm25": models.Document(text=page_text_ or f"page {page_no}", model="Qdrant/bm25")},
                payload={"id": doc_id, "doc": doc, "page": page_no, "kind": "image", "seq": -1,
                         "text": page_text_[:400], "pdf_path": pdf_path}))   # reference, NOT the blob
            lines = page_text_.splitlines()
        else:
            lines = pymupdf4llm.to_markdown(pdf, pages=[page_no - 1]).splitlines()

        # STEP 2 - split the lines into blocks: list items vs normal text
        blocks = split_page(lines)

        # STEP 3 - every block becomes units; items carry their number + which list they belong to
        units = []
        for blk in blocks:
            no = item_number(blk["text"]) if blk["type"] == "item" else None
            if no is not None:
                if last_no is None or no <= last_no:           # no previous number, or numbering
                    list_id += 1                               # restarted -> a NEW list begins
                last_no = no
                stats["items"] += 1
                units.append({"payload": {"kind": "item", "item_no": no, "list_id": list_id},
                              "text": blk["text"]})
            else:
                for u in to_units(blk["text"]):                # long prose still gets chunked!
                    units.append({"payload": {"kind": "chunk"}, "text": u})

        if last_no is not None and not any(b["type"] == "item" for b in blocks):
            last_no = None                                     # a page with no items ends the list

        if units:
            vecs = await embed_texts([u["text"] for u in units])
            for seq, vector in enumerate( vecs):
                unit = units[seq]
                pts.append(models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"dense": vector,
                            "bm25": models.Document(text=unit["text"] or " ", model="Qdrant/bm25")},
                    payload={"id": doc_id, "doc": doc, "page": page_no, "seq": seq,
                             "text": unit["text"], **unit["payload"]}))

        if pts:
            await qdr.upsert(COLLECTION, points=pts)
            total = page_no

    await set_hash(doc_id, doc, h)
    pdf.close()
    qdr_count = await qdr.count(COLLECTION)
    print(f"{doc_id} - {doc}: {stats['text']}txt/{stats['image']}img pages, items={stats['items']}, "
          f"points={qdr_count.count}")
    return total


async def sample_document_text(limit_chars: int = 6000) -> str:
    """Grab some stored text from the collection (used to auto-build guardrails)."""
    qdr = qdrant_client()
    points, _ = await qdr.scroll(settings.qdrant_collection, limit=40, with_payload=True)
    chunks = [p.payload.get("text", "") for p in points if p.payload.get("text")]
    return "\n\n".join(chunks)[:limit_chars]


async def delete_document_vectors(doc_id: int) -> None:
    """Remove every vector belonging to one document (fast: doc_id is a payload index)."""
    qdr = qdrant_client()
    await qdr.delete(
        settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(must=[
                models.FieldCondition(key="id", match=models.MatchValue(value=doc_id))
            ])
        ),
    )
