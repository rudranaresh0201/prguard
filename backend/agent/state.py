from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # full conversation history
    query: str                                 # original user query
    route: Literal["rag", "web", "both", "unclear"]  # router's decision
    rag_results: list[dict]                    # chunks from your existing RAG
    web_results: list[dict]                    # Tavily search results
    final_answer: str                          # synthesis output
    agent_steps: list[str]                     # live steps for SSE streaming
