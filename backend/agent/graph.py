from langgraph.graph import StateGraph, END
from backend.agent.state import AgentState
from backend.agent.nodes import router_node, rag_node, web_node, synthesis_node, clarify_node

def route_decision(state: AgentState) -> str:
    return state["route"]

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router",    router_node)
    graph.add_node("rag",       rag_node)
    graph.add_node("web",       web_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("clarify",   clarify_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges("router", route_decision, {
        "rag":     "rag",
        "web":     "web",
        "both":    "rag",
        "unclear": "clarify",
    })
    graph.add_conditional_edges("rag",
        lambda s: "web" if s["route"] == "both" else "synthesis",
        {"web": "web", "synthesis": "synthesis"}
    )
    graph.add_edge("web",       "synthesis")
    graph.add_edge("synthesis", END)
    graph.add_edge("clarify",   END)
    return graph.compile()

agent_graph = build_graph()
