from typing import List

from langsmith import traceable
from pydantic import BaseModel

from app.config import get_settings
settings = get_settings()
from langchain_core.messages import HumanMessage
from qdrant_client import models

from app.rag.clients import openai_client_final, openai_client_planner, qdrant_client
from app.rag.ingest import load_pages, page_text
from app.rag.retrieve import hybrid_search, rerank
from concurrent.futures import ThreadPoolExecutor

class RelevantIdx(BaseModel):
    relevant: List[int]

async def grade_chunks(question, docs):
    numbered = "\n\n".join(f"[{i}] {d['text'][:400]}" for i, d in enumerate(docs))
    llm = openai_client_planner()
    idx = llm.with_structured_output(RelevantIdx).invoke([HumanMessage(
        f"Question: {question}\n\nChunks:\n{numbered}\n\n Which chunk indices help answer it?")]).relevant
    
    return [docs[i] for i in idx if i < len(docs)]

ANSWER_RULES = ("Answer ONLY from the context. If not in context, say you don't know.\n"
                "If asked to LIST entries/rows, extract EVERY one that belongs — a section continues "
                "until the next section marker; do not stop early.\n"
                "Never invent numbers; if asked for a computed total, show the values you used.\n\n")

####Lookup service
@traceable(name="lookup_service")
async def s_lookup(question, doc=None, pages=None):
    docs = await rerank(question, await hybrid_search(question, doc=doc))
    kept = await grade_chunks(question, docs)                        # CRAG: grade
    if not kept: 
        llm = openai_client_planner()                                              # CRAG: rewrite + retry
        nq = llm.invoke([HumanMessage(
            f"Retrieval failed for: {question}\nRewrite it with different, more specific keywords.")]).content

        kept = await grade_chunks(question, await rerank(nq, await hybrid_search(nq, doc=doc))) or docs[:4]

    page_keys = []                                             # PAGE EXPANSION: chunks find pages,
    for d in kept:                                             # the FULL pages answer
        k = (d["doc"], d["page"])
        if k not in page_keys: page_keys.append(k)
        
    parts = []
    for doc_, pg in page_keys[:3]:
        full = await page_text(doc_, pg)
        parts.append(f"[{doc_} p.{pg}]\n{full[:6000]}")
        
    ctx = "\n\n".join(parts)
    vlm = openai_client_final()
    ans = vlm.invoke([HumanMessage(f"{ANSWER_RULES}Context:\n{ctx}\n\nQuestion: {question}")]).content
    return ans, ctx

### Listall Service
@traceable(name="list_service")
async def s_list_all(question, doc=None, pages=None):
    # STEP 1 — LOCATE: search with the QUESTION (items and chunks both count as clues)
    hits = await hybrid_search(question, k=8, doc=doc)
    candidates = []   
                                        # (doc, list_id), best-ranked first
    for h in hits:
        found = ([(h["doc"], h["list_id"])] if h.get("kind") == "item"
                 else await lists_on_page(h["doc"], h["page"]))      # a heading/chunk points to its page's lists

        for key in found:
            if key not in candidates:
                candidates.append(key)
                
    if not candidates:
        return await s_lookup(question, doc)                         # no list found near this question
    
    # STEP 2 — COMPLETE: scroll ONLY the top-ranked list(s), with the completeness proof
    sections = []
    for d, lid in candidates[:2]:                              # at most 2 lists ever reach the LLM
        entries = await scroll_list(d, lid)
        nos = sorted(entries)
        
        listing = "\n".join(entries[n]["text"].replace(chr(10), " ")[:300] for n in nos)
        sections.append(listing)
        
    evidence = "\n\n".join(sections)

    # STEP 3 — FORMAT (unchanged): the LLM sees only the relevant list(s), never the whole corpus
    llm = openai_client_planner()
    ans = llm.invoke([HumanMessage(
        f"{question}\n\nItemized lists extracted from the documents:\n\n{evidence}\n\n"
        f"Use ONLY the list relevant to the question. Format every relevant entry. Do not invent "
        f"or drop entries. If NONE of the list is relevant to the question, reply exactly: NOT_IN_LISTS")]).content

    if ans.strip().startswith("NOT_IN_LISTS"):
        return await s_lookup(question, doc)

    return ans, evidence

async def scroll_list(d, lid):
    qdr = qdrant_client()
    """Fetch EVERY item of ONE specific list — bounded work, whatever the corpus size."""
    must = [models.FieldCondition(key="kind",    match=models.MatchValue(value="item")),
            models.FieldCondition(key="doc",     match=models.MatchValue(value=d)),
            models.FieldCondition(key="list_id", match=models.MatchValue(value=lid))]
    entries = {} 
    offset = None
    while True:
        pts, offset = await qdr.scroll(settings.qdrant_collection, scroll_filter=models.Filter(must=must),
                                 limit=100, offset=offset, with_payload=True)
        for p in pts:
            entries[p.payload["item_no"]] = p.payload
        if offset is None: break
    return entries

async def lists_on_page(d, pg):
    qdr = qdrant_client()
    """Which lists have items on this page? (lets a 'References' HEADING locate its list)"""
    must = [models.FieldCondition(key="kind", match=models.MatchValue(value="item")),
            models.FieldCondition(key="doc",  match=models.MatchValue(value=d)),
            models.FieldCondition(key="page", match=models.MatchValue(value=pg))]
    
    pts, _ = await qdr.scroll(settings.qdrant_collection, scroll_filter=models.Filter(must=must), limit=50, with_payload=True)

    return [(p.payload["doc"], p.payload["list_id"]) for p in pts]


### Sumamrize service
@traceable(name="summarize_service")
async def s_summarize(question, doc=None, pages=None):
    rows = await load_pages(doc, pages)
    if not rows: return "No text found for that document/pages.", ""

    by_doc = {}                                                # one summary tree PER document —
    for d, pg, txt in rows:                                    # documents never mix in a batch
        by_doc.setdefault(d, []).append((d, pg, txt))
    
    partials = [f"--- summary of {d} ---\n{summarize_doc(d, drows)}"
                for d, drows in sorted(by_doc.items())]
    evidence = "\n\n".join(partials)
    llm = openai_client_planner()
    ans = llm.invoke([HumanMessage(
        f"Using these document summaries, answer: {question}\n"
        f"Keep a clearly-labelled section per document if several are involved. "
        f"Match the requested length ('in short' means brief).\n\n{evidence}")]).content
    print("Result: ", len(ans))
    return ans, evidence


def make_batches(parts, max_chars=settings.max_batch):
    """Pack parts into batches of at most max_chars each."""
    batches, cur, size = [], [], 0
    
    for p in parts:
        if cur and size + len(p) > max_chars:
            batches.append("\n\n".join(cur)); 
            cur, size = [], 0
            
        cur.append(p); 
        size += len(p)
        
    if cur: batches.append("\n\n".join(cur))
    return batches

def summarize_batches(batches):
    """One summary per batch — run in PARALLEL (they are independent)."""
    def one(b):
        print("\n\n Batch: ", b)
        llm = openai_client_planner()
        return llm.invoke([HumanMessage(
            f"Summarize the key points (keep page references):\n\n{b}")]).content
        
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(one, batches))

def summarize_doc(d, rows):
    """HIERARCHICAL summarization: summarize pages -> summaries of summaries -> ... until
    everything fits in ONE prompt. Every call is bounded, whatever the document size."""
    
    parts = [f"[{d} page {pg}]\n{txt}" for _, pg, txt in rows]
    level = 0
    while sum(len(p) for p in parts) > settings.max_batch:
        batches = make_batches(parts)
        # print(f"  {d} level {level}: {len(parts)} parts -> {len(batches)} batches")
        parts = summarize_batches(batches)                     # each summary ~10x smaller
        level += 1
    return "\n\n".join(parts)

###Visual Service
@traceable(name="visual_service")
async def s_visual(question, doc=None, pages=None):
    hits = await hybrid_search(question, k=2, doc=doc, kind="image")
    if not hits:
        return await s_lookup(question, doc)
    
    content = [{"type": "text", "text": f"Answer from these document page images. Cite doc and page.\n"
                                        f"Question: {question}"}]
    for h in hits:
        content.append({"type": "text", "text": f"[{h['doc']} p.{h['page']}]"})
        content.append({"type": "image_url", "image_url": {"url": h["image"]}})

    vlm = openai_client_final()
    ans = vlm.invoke([HumanMessage(content=content)]).content
    evidence = "\n".join(f"[{h['doc']} p.{h['page']}] text: {h['text'][:200]}" for h in hits)
    return ans, evidence