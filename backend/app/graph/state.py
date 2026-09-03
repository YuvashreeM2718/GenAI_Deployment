"""
Shared state that flows through every LangGraph node.
Keep this the single source of truth -- nodes only read/write this dict.
"""

from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Fixed order we collect slots in -- matches the example conversation
# (property type is usually mentioned first, then we ask for the rest).
SLOT_ORDER = ["property_type", "budget", "location", "style"]

DEFAULT_SLOTS = {
    "property_type": None,
    "budget": None,
    "location": None,
    "style": None,
}


class ConversationState(TypedDict, total=False):
    session_id: str
    # add_messages reducer appends new messages instead of overwriting history
    messages: Annotated[list[BaseMessage], add_messages]

    intent: Optional[str]                  # "new_quotation" | "faq" | "unclear"
    slots: dict                            # see DEFAULT_SLOTS keys
    missing_slots: list[str]
    next_action: str                       # "ask" | "proceed"

    rag_context: Optional[list[dict]]
    quote_breakdown: Optional[dict]
    quote_total: Optional[int]
    budget_diff_pct: Optional[float]
    over_budget: Optional[bool]

    mcp_result: Optional[dict]
    reply: Optional[str]
