from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..retrieval import retrieve_chunks
from ..llm_router import generate_answer

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    document_id: str | None = None


@router.post("/query")
def query_documents(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    result = retrieve_chunks(req.query, top_k=req.top_k, document_id=req.document_id)

    if result["guard_fired"]:
        return {
            "answer": "No relevant context found in the documents.",
            "sources": [],
            "guard_fired": True,
            "retrieval_score": None,
            "status": result.get("status", "no_context"),
        }

    answer = generate_answer(req.query, result["context"])
    return {
        "answer": answer,
        "sources": result["chunks"],
        "guard_fired": False,
        "retrieval_score": result.get("retrieval_score"),
        "status": result.get("status", "ok"),
    }
