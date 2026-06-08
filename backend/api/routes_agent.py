from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
from backend.agent.graph import agent_graph
from backend.agent.state import AgentState

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentRequest(BaseModel):
    query: str

@router.post("/query")
async def agent_query(req: AgentRequest):
    initial_state: AgentState = {
        "messages": [], "query": req.query, "route": "rag",
        "rag_results": [], "web_results": [], "final_answer": "", "agent_steps": [],
    }
    result = await agent_graph.ainvoke(initial_state)
    return {
        "answer": result["final_answer"],
        "route": result["route"],
        "steps": result["agent_steps"],
        "rag_sources": [r.get("filename") or r.get("source") for r in result["rag_results"]],
        "web_sources": [r.get("source") for r in result["web_results"]],
    }

@router.post("/query/stream")
async def agent_query_stream(req: AgentRequest):
    initial_state: AgentState = {
        "messages": [], "query": req.query, "route": "rag",
        "rag_results": [], "web_results": [], "final_answer": "", "agent_steps": [],
    }
    async def event_generator():
        async for event in agent_graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            if kind == "on_chain_start" and event.get("name") in ["router","rag","web","synthesis","clarify"]:
                yield f"data: {json.dumps({'type':'step','node':event['name']})}\n\n"
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                if chunk:
                    yield f"data: {json.dumps({'type':'token','content':chunk})}\n\n"
            if kind == "on_chain_end" and event.get("name") == "LangGraph":
                output = event["data"].get("output", {})
                yield f"data: {json.dumps({'type':'done','route':output.get('route',''),'steps':output.get('agent_steps',[])})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
