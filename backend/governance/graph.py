from langgraph.graph import StateGraph, END
from backend.governance.state import PRState
from backend.governance.nodes import (
    triage_node,
    context_retrieval_node,
    security_node,
    docs_node,
    gate_aggregator_node,
    merge_node,
    no_merge_node,
    audit_node,
)

def gates_decision(state: PRState) -> str:
    return "merge" if state["gates_passed"] else "no_merge"

def build_governance_graph():
    graph = StateGraph(PRState)

    graph.add_node("triage",            triage_node)
    graph.add_node("context_retrieval", context_retrieval_node)
    graph.add_node("security",          security_node)
    graph.add_node("docs",            docs_node)
    graph.add_node("gate_aggregator", gate_aggregator_node)
    graph.add_node("merge",           merge_node)
    graph.add_node("no_merge",        no_merge_node)
    graph.add_node("audit",           audit_node)

    graph.set_entry_point("triage")
    graph.add_edge("triage",            "context_retrieval")
    graph.add_edge("context_retrieval", "security")
    graph.add_edge("security",  "docs")
    graph.add_edge("docs",      "gate_aggregator")

    graph.add_conditional_edges(
        "gate_aggregator",
        gates_decision,
        {"merge": "merge", "no_merge": "no_merge"}
    )

    graph.add_edge("merge",    "audit")
    graph.add_edge("no_merge", "audit")
    graph.add_edge("audit",    END)

    return graph.compile()

governance_graph = build_governance_graph()
