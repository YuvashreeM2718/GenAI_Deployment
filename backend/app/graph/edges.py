"""
Conditional routing between nodes. Plain if/else on state values -- no LLM
calls here, the LLM already made its decision inside the node.
"""


def route_after_intent(state: dict) -> str:
    if state.get("intent") == "new_quotation":
        return "slot_extractor"
    return "faq_responder"


def route_after_intake(state: dict) -> str:
    if state.get("missing_slots"):
        return "responder"
    return "rag_search"
