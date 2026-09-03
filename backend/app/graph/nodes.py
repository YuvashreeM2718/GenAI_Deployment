"""
Node functions for the quotation agent graph.
Each node takes the full ConversationState and returns only the fields it
updates -- LangGraph merges the rest in automatically.

Kept intentionally simple:
- Intent classification & slot extraction use one structured LLM call each
  (Pydantic schema in, validated object out -- LangChain/Ollama handle the
  JSON parsing, we never touch json.loads directly).
- Everything else (missing-slot checks, cost totals, budget comparison)
  is plain Python -- no custom scoring/ranking logic.
"""

from app.graph.schemas import IntentResult, SlotExtraction
from app.graph.state import DEFAULT_SLOTS, SLOT_ORDER
from app.llm.ollama_client import get_chat_model, get_structured_model
from app.mcp.mcp_client import call_mcp_tool
from app.rag.qdrant_client import search_pricing

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

INTENT_SYSTEM_PROMPT = """You classify a user's message for an interior design quotation chatbot."""

SLOT_EXTRACT_SYSTEM_PROMPT = """Extract interior design quotation details from the user's latest message only.
Only fill a field if it is explicitly mentioned in this message -- leave everything else null."""

FAQ_SYSTEM_PROMPT = """You are a friendly assistant for an interior design company.
Answer briefly and, where relevant, invite the user to start a quotation."""

SLOT_QUESTIONS = {
    "property_type": "Sure, I can help prepare your quotation. What type of property is it (e.g. 2BHK, 3BHK)?",
    "budget": "Great. What is your approximate budget for the interiors?",
    "location": "Which city is the property located in?",
    "style": "What style do you prefer — modern, contemporary, traditional, or minimal?",
}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def intent_agent(state: dict) -> dict:
    """Classify intent -- but skip re-classifying if we're mid-intake for a quotation."""
    if state.get("intent") == "new_quotation" and state.get("missing_slots"):
        return {}

    last_message = state["messages"][-1].content
    model = get_structured_model(IntentResult)
    result: IntentResult = model.invoke(
        [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": last_message},
        ]
    )
    return {"intent": result.intent}


def slot_extractor(state: dict) -> dict:
    """Pull structured slot values out of the latest user message and merge them in."""

    last_message = state["messages"][-1].content
    model = get_structured_model(SlotExtraction)
    extracted: SlotExtraction = model.invoke(
        [
            {"role": "system", "content": SLOT_EXTRACT_SYSTEM_PROMPT.join(DEFAULT_SLOTS)},
            {"role": "user", "content": last_message},
        ]
    )
    slots = dict(state.get("slots") or DEFAULT_SLOTS)
    extracted_dict = extracted.model_dump()
    for field in SLOT_ORDER:
        value = extracted_dict.get(field)
        if value not in (None, "", "null"):
            slots[field] = value
    return {"slots": slots}


def intake_agent(state: dict) -> dict:
    """Check which slots are still missing; ask for exactly one at a time."""
    slots = state.get("slots") or DEFAULT_SLOTS
    missing = [field for field in SLOT_ORDER if not slots.get(field)]

    if missing:
        next_field = missing[0]
        return {
            "missing_slots": missing,
            "next_action": "ask",
            "reply": SLOT_QUESTIONS[next_field],
        }

    return {"missing_slots": [], "next_action": "proceed"}


def rag_search_node(state: dict) -> dict:
    
    """Retrieve relevant pricing line items from Qdrant for the collected slots."""
    slots = state["slots"]
    query = f"{slots['property_type']} {slots['style']} interior design cost"

    results = search_pricing(
        query=query,
        city=slots["location"],
        style=slots["style"],
        top_k=10,
    )

    return {"rag_context": results}


def quote_agent(state: dict) -> dict:
    """Sum retrieved line items into a breakdown + total, and check against budget."""
    items = state.get("rag_context") or []

    breakdown = {}
    for item in items:
        category = item.get("category")
        price = item.get("price", 0)
        if category and category not in breakdown:
            breakdown[category] = price

    total = sum(breakdown.values())
    budget = state["slots"].get("budget") or 0
    diff_pct = round(((total - budget) / budget) * 100, 1) if budget else 0.0
    over_budget = diff_pct > 10

    return {
        "quote_breakdown": breakdown,
        "quote_total": total,
        "budget_diff_pct": diff_pct,
        "over_budget": over_budget,
    }


async def mcp_tool_node(state: dict) -> dict:
    """
    Deterministic pipeline: create_quotation -> generate_pdf.
    (send_email / save_lead / schedule_design_consultation are wired in
    once contact-capture is added -- kept out of the base flow for now.)
    """

    slots = state["slots"]
    quote_payload = {
        "session_id": state["session_id"],
        "property_type": slots["property_type"],
        "location": slots["location"],
        "budget": slots["budget"],
        "style": slots["style"],
        "breakdown": state["quote_breakdown"],
        "total": state["quote_total"],
    }

    quotation = await call_mcp_tool("create_quotation", quote_payload)
    pdf = await call_mcp_tool("generate_pdf", {"quotation_id": quotation.get("quotation_id")})

    return {"mcp_result": {"quotation": quotation, "pdf": pdf}}


def responder_node(state: dict) -> dict:
    """Format the final reply. If we're mid-intake, the question is already set."""
    if state.get("next_action") == "ask":
        return {}

    breakdown = state.get("quote_breakdown") or {}
    total = state.get("quote_total") or 0

    lines = [f"- {category}: ₹{price:,}" for category, price in breakdown.items()]
    reply = "Here's your estimated quotation:\n\n" + "\n".join(lines)
    reply += f"\n\nEstimated Total: ₹{total:,}"

    if state.get("over_budget"):
        budget = state["slots"].get("budget", 0)
        reply += (
            f"\n\nNote: this is about {state['budget_diff_pct']}% over your stated budget "
            f"of ₹{budget:,}. We can adjust scope to fit your budget."
        )

    pdf_url = ((state.get("mcp_result") or {}).get("pdf") or {}).get("url")
    if pdf_url:
        reply += f"\n\nYour PDF quote is ready: {pdf_url}"

    return {"reply": reply}


async def faq_responder(state: dict) -> dict:
    """Short LLM answer for non-quotation messages (FAQ / small talk)."""
    last_message = state["messages"][-1].content
    model = get_chat_model()
    response_parts = []

    async for chunk in model.astream(
        [
            {"role": "system", "content": FAQ_SYSTEM_PROMPT},
            {"role": "user", "content": last_message},
        ]
    ):
        if chunk.content:
            response_parts.append(chunk.content)

    return {"reply": "".join(response_parts)}
