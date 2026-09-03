"""
Wires nodes and edges into the quotation agent graph.
Returns an uncompiled StateGraph -- the caller (app startup) compiles it
with a checkpointer so conversation state persists across turns.
"""

from langgraph.graph import END, START, StateGraph

from app.graph import edges, nodes
from app.graph.state import ConversationState


def build_graph_definition() -> StateGraph:
    graph = StateGraph(ConversationState)

    graph.add_node("intent_agent", nodes.intent_agent)
    graph.add_node("slot_extractor", nodes.slot_extractor)
    graph.add_node("intake_agent", nodes.intake_agent)
    graph.add_node("rag_search", nodes.rag_search_node)
    graph.add_node("quote_agent", nodes.quote_agent)
    graph.add_node("mcp_tool_node", nodes.mcp_tool_node)
    graph.add_node("responder", nodes.responder_node)
    graph.add_node("faq_responder", nodes.faq_responder)

    graph.add_edge(START, "intent_agent")

    graph.add_conditional_edges(
        "intent_agent",
        edges.route_after_intent,
        {"slot_extractor": "slot_extractor", "faq_responder": "faq_responder"},
    )

    graph.add_edge("slot_extractor", "intake_agent")

    graph.add_conditional_edges(
        "intake_agent",
        edges.route_after_intake,
        {"responder": "responder", "rag_search": "rag_search"},
    )

    graph.add_edge("rag_search", "quote_agent")
    graph.add_edge("quote_agent", "mcp_tool_node")
    graph.add_edge("mcp_tool_node", "responder")
    graph.add_edge("responder", END)
    graph.add_edge("faq_responder", END)

    return graph
