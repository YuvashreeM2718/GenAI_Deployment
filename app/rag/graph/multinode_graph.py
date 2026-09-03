from typing import Literal

from langsmith import traceable

from app.config import get_settings
from app.guardrails.engine import guard_input
from app.rag.cache import lookup, store
from app.rag.graph.model_graph import CacheState, PlanCoverage, PlannedSub, QueryPlan, RAGState, Reflection
from app.rag.graph.node_service import s_list_all, s_lookup, s_summarize, s_visual
settings = get_settings()
from app.rag.clients import openai_client_planner, qdrant_client
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from qdrant_client import models
from langgraph.types import Send

async def corpus_card():
    qdr = qdrant_client()
    pts, _ = await qdr.scroll(settings.qdrant_collection, scroll_filter=models.Filter(must=[
        models.FieldCondition(key="kind", match=models.MatchValue(value="manifest"))]),
        limit=100, with_payload=True)
    return f"Ingested documents: {sorted(p.payload['doc'] for p in pts)}"

STRATEGIES = {"lookup": s_lookup, "list_all": s_list_all, "summarize": s_summarize, "visual": s_visual}

PLAN_RULES = """Split the question ONLY if it asks about multiple unrelated things or MULTIPLE documents.
NEVER drop any part. Related facets about the same topic MERGE into one complete sub-question.
If the question names multiple documents, make one sub-question per document.
Strategies:
- list_all: enumerate EVERY entry of a numbered/itemized list in the documents (references,
  bibliography, glossary, clauses).
- summarize: summarize a whole document or specific pages.
- visual: charts, scanned pages, photos, diagrams, 'what does the figure show'.
- lookup: everything else (specific facts, terms, explanations, best-effort numeric questions).
Examples:
- 'List all the reference papers and their authors' -> 1 sub (list_all)
- 'Summarize the complete document' -> 1 sub (summarize)
- 'What optimizer was used and what are its parameters?' -> 1 sub (lookup): 'What optimizer and which exact parameter values were used to train the model?'
- 'What does the chart show and summarize page 3?' -> 2 subs (visual + summarize)
- 'all authors of this paper, and background of this paper' -> 2 subs (lookup: authors · lookup: background) — TWO different information needs, never drop one
The above are the examples, based on the question choose the appropriate strategies.
"""

llm = openai_client_planner()
planner = llm.with_structured_output(QueryPlan)

async def _guard(state: RAGState) -> RAGState:
    """Topical guardrail — runs FIRST, before the router. Off-topic -> fixed refusal, skip everything."""
    allowed, message = await guard_input(state["question"])
    if allowed:
        return {"route": "allow"}

    return {"route": "blocked", "cache_results": [{ "answer": message, "sources": [], "cached": False }]}


async def n_plan(state: RAGState) -> RAGState:
    prompt = f"{PLAN_RULES}\n\n{await corpus_card()}\n\nUser question: {state['question']}"
    
    plan = planner.invoke([HumanMessage(prompt)])
    
    def coverage_gap(subs_):
        return llm.with_structured_output(PlanCoverage).invoke([HumanMessage(
            f"Original question: {state['question']}\n"
            f"Planned sub-questions: {[p.question for p in subs_]}\n"
            f"Name a requirement EXPLICITLY WORDED in the original that NO sub-question covers. "
            f"Do NOT invent requirements the user never asked for. Reply '' if fully covered.")]).missing.strip()

    missing = coverage_gap(plan.subs)
    if missing:
        print(f"  plan check: missing '{missing[:60]}' -> re-planning")
        plan = planner.invoke([HumanMessage(
            prompt + f"\n\nYour previous plan missed this requirement: {missing}. Cover it.")])
        
        missing = coverage_gap(plan.subs)

        if missing:                                   
            plan.subs.append(PlannedSub(         
                question=f"{missing} (regarding: {state['question']})",
                strategy="lookup", doc=plan.subs[0].doc if plan.subs else None, pages=[]
                                    )
                             )

    subs = [s.model_dump() for s in plan.subs]
    return {"subs": subs}

async def cache_lookup(state: RAGState):
    # 1) semantic cache: similar question already answered? return instantly.

    for sub in state["subs"]:
        cache_state : CacheState = {}
        state["cache_results"] = []
        question = sub["question"]
        hit = await lookup(question)
        if hit:
            cache_state["answer"], cache_state["sources"] = hit
            cache_state["cached"] = True
            state["cache_results"].append(cache_state)
            cache_state = {}

    return state
    

def route_after_cache(state: RAGState):

    is_cached = any(item["cached"] for item in state["cache_results"])
    # Cache HIT
    if is_cached:
        return "end"

    # Cache MISS → fan out
    return [
        Send(
            sub["strategy"],
            {
                "sub": {
                    **sub,
                    "i": i
                }
            }
        )
        for i, sub in enumerate(state["subs"])
    ]


async def fan_out(state: RAGState):
    return [Send(s["strategy"], {"sub": {**s, "i": i}}) for i, s in enumerate(state["subs"])]

def make_strategy_node(name, fn):
    async def node(payload):                                         # payload = one Send's data
        sub = payload["sub"]
        ans, ev = await fn(sub["question"], sub.get("doc"), sub.get("pages"))
        
        return {"results": [{"i": sub["i"], "question": sub["question"],
                             "answer": ans, "evidence": ev}]}  # APPENDED via the operator.add reducer
    node.__name__ = name
    return node

async def n_combine(state):
    rs = sorted(state["results"], key=lambda r: r["i"]) 
    if len(rs) == 1:
        return {"answer": rs[0]["answer"]}
    
    parts = "\n\n".join(f"Q: {r['question']}\nA: {r['answer']}" for r in rs)
    print("Call Start: ")
    ans = llm.invoke([HumanMessage(
        f"Merge into ONE coherent reply to: {state['question']}\nKeep citations, add no new facts.\n\n{parts}")]).content
    print("Combine Node Called: ", ans)
    return {"answer": ans}


async def n_verify(state):
    """SELF-RAG: grounded AND useful, else loop back for better context (retry-limited)."""
    
    ev = "\n\n".join(r["evidence"] for r in state["results"])[:12000]
    r = llm.with_structured_output(Reflection).invoke([HumanMessage(
        f"User question: {state['question']}\n\nEvidence gathered from the documents:\n{ev}\n\n"
        f"Answer:\n{state['answer']}\n\n"
        f"grounded: is every claim supported by the evidence? "
        f"useful: does the answer address EVERY part of the question? If it asks for X AND Y "
        f"(e.g. authors AND background), BOTH must be present — one missing means useful=false.")])
    
    if r.grounded and r.useful:
        return {"verdict": "accept"}
    
    if state.get("retries", 0) >= 2:
        print("  Self-RAG: retry limit reached -> accepting with caveat")
        return {"verdict": "accept",
                "answer": state["answer"] + "\n\n_Note: this answer could not be fully "
                                            "verified/completed from the documents._"}
                                            
    why = "not grounded" if not r.grounded else "incomplete for the question"
    fix_q = llm.invoke([HumanMessage(
        f"The current answer to '{state['question']}' has this problem: {r.problem or why}. "
        f"Write ONE precise, standalone search question that would retrieve the missing or "
        f"correct information. Return only the question.")]).content.strip()
    print(f"  Self-RAG: {why} -> looping back to retrieve: {fix_q[:70]}")
    
    fix = {"question": fix_q, "strategy": "lookup",
           "doc": state["subs"][0].get("doc") if state["subs"] else None,
           "pages": [], "i": 900 + state.get("retries", 0)}    # sorts after the originals
    return {"verdict": "refine", "fix": fix, "retries": state.get("retries", 0) + 1}

async def after_verify(state):
    if state["verdict"] == "accept":
        return "cache_store"
    return Send(state["fix"]["strategy"], {"sub": state["fix"]})   # loop-back = one more Send

async def cache_store(state: RAGState):
    # ---remember it for next time
    question = state["question"]
    answer = state["answer"]
    sources = [ r["evidence"] for r in state["results"]]
    await store(question, answer, sources)
    cacheState : CacheState = {}
    cacheState["answer" ] = answer
    cacheState["sources"] = sources
    cacheState["cached"] = False
    state["cache_results"] = [cacheState]
    return state


def _build_graph():
    g = StateGraph(RAGState)
    
    # ---- guardrail (NeMo) — before anything else ----
    g.add_node("guard",_guard)
    
    # ---- NODES: one line per node, nothing hidden ----
    g.add_node("plan",      n_plan)                                    # splits + routes the question
    g.add_node("cache_lookup", cache_lookup)
    g.add_node("lookup",    make_strategy_node("lookup",    s_lookup))     # facts & explanations
    g.add_node("list_all",  make_strategy_node("list_all",  s_list_all))   # numbered lists, with proof
    g.add_node("summarize", make_strategy_node("summarize", s_summarize))  # whole doc / pages
    g.add_node("visual",    make_strategy_node("visual",    s_visual))     # charts & scanned pages
    g.add_node("combine",   n_combine)                                 # merge all sub-answers
    g.add_node("verify",    n_verify)                                  # Self-RAG: grounded? useful?
    g.add_node("cache_store", cache_store)                             # redis cache store

    # ---- EDGES ----
    g.add_edge(START, "guard")
    # blocked -> straight to END with the fixed refusal; allowed -> the router
    g.add_conditional_edges("guard", lambda s: s["route"], {"allow": "plan", "blocked": END})

    g.add_edge("plan", "cache_lookup")
    g.add_conditional_edges("cache_lookup",route_after_cache,{"lookup":    "lookup",
                            "list_all":  "list_all",
                            "summarize": "summarize",
                            "visual":    "visual",
                            "end":       END})

    # plan fans OUT: fan_out() returns one Send per sub-question -> these nodes run IN PARALLEL
    # g.add_conditional_edges("fan_out", fan_out,
    #                     ["lookup", "list_all", "summarize", "visual"])

    # every strategy fans IN to combine (combine waits until ALL parallel branches finish)
    g.add_edge("lookup",    "combine")
    g.add_edge("list_all",  "combine")
    g.add_edge("summarize", "combine")
    g.add_edge("visual",    "combine")

    g.add_edge("combine", "verify")

    # verify either accepts (-> END) or loops BACK into a strategy with a corrective question
    g.add_conditional_edges("verify", after_verify,
                        {"lookup":    "lookup",
                        "list_all":  "list_all",
                        "summarize": "summarize",
                        "visual":    "visual",
                        "cache_store": "cache_store"})

    g.add_edge("cache_store",END)

    return g.compile()


chat_graph = _build_graph()

@traceable(name="generate_function")
async def run_chat(question: str) -> RAGState :
    """Entry point used by the /chat endpoint. The caller must set the user in the ContextVar first."""
    final : RAGState = await chat_graph.ainvoke({"question": question})
    print("\n" + "=" * 80 + "\n" + final.get("cache_results")[0]["answer"])
    return final.get("cache_results")[0]