from langchain_groq import ChatGroq
from tavily import TavilyClient
from backend.retrieval import retrieve_chunks
from backend.llm import generate_answer
from backend.agent.state import AgentState
import os

from backend.config import GROQ_MODEL, RAG_TOP_K, AGENT_WEB_RESULTS
llm = ChatGroq(model=GROQ_MODEL, api_key=os.getenv("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def router_node(state: AgentState) -> AgentState:
    prompt = f"""Classify this query into exactly one word: rag, web, both, or unclear.

Rules:
- rag: questions about internal documents, uploaded files, company policies, specific stored knowledge
- web: current events, live prices, news, anything time-sensitive
- both: needs internal context AND live web data together
- unclear: genuinely cannot determine intent

Default to rag unless the query clearly needs live/current information.

Query: {state['query']}
Reply with one word only."""
    result = llm.invoke(prompt)
    route = result.content.strip().lower()
    if route not in ["rag", "web", "both", "unclear"]:
        route = "rag"
    return {**state, "route": route, "agent_steps": state["agent_steps"] + [f"🔀 Router → {route}"]}

def rag_node(state: AgentState) -> AgentState:
    rewrite_prompt = f"""Rewrite this question as 3-5 keyword search terms only.
No sentences. Just the most important nouns and named entities.
Question: {state['query']}
Keywords:"""
    rewritten = llm.invoke(rewrite_prompt).content.strip()
    search_query = rewritten if rewritten else state["query"]
    result = retrieve_chunks(query=search_query, top_k=RAG_TOP_K)
    chunks = [
        {
            "text": c["text"],
            "source": c.get("doc_id", ""),
            "filename": c.get("file", "") or c.get("metadata", {}).get("file", "") or c.get("metadata", {}).get("source", ""),
            "score": c.get("score"),
            "page": c.get("page")
        }
        for c in result["chunks"]
    ]
    return {**state, "rag_results": chunks, "agent_steps": state["agent_steps"] + [f"📚 RAG → {len(chunks)} chunks retrieved"]}

def web_node(state: AgentState) -> AgentState:
    results = tavily_client.search(query=state["query"], max_results=AGENT_WEB_RESULTS)
    web_docs = [
        {"text": r["content"], "source": r["url"], "title": r.get("title", "")}
        for r in results.get("results", [])
    ]
    return {**state, "web_results": web_docs, "agent_steps": state["agent_steps"] + [f"🌐 Web → {len(web_docs)} results"]}

def synthesis_node(state: AgentState) -> AgentState:
    context_parts = []
    if state["rag_results"]:
        context_parts.append("Internal Docs:\n" + "\n".join([f"- {r['text']}" for r in state["rag_results"]]))
    if state["web_results"]:
        context_parts.append("Web Results:\n" + "\n".join([f"- {r['title']}: {r['text']}" for r in state["web_results"]]))
    full_context = "\n\n".join(context_parts)
    prompt = f"""You are a precise research assistant. Answer the query completely using the context below.

Rules:
- List ALL relevant items found, never stop at the first match
- Use bullet points for lists
- Report everything present even if context is partial
- Never truncate lists or stop after one example

Context:
{full_context}

Query: {state['query']}

Comprehensive answer:"""
    import re
    answer = llm.invoke(prompt).content.strip()
    answer = re.sub(r'\*+', '', answer).strip()
    return {**state, "final_answer": answer, "agent_steps": state["agent_steps"] + ["✅ Synthesis complete"]}

def clarify_node(state: AgentState) -> AgentState:
    return {**state, "final_answer": "Could you clarify your query? I need more context to know whether to search internal docs or the web.", "agent_steps": state["agent_steps"] + ["❓ Clarification requested"]}
