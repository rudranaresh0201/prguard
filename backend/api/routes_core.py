from __future__ import annotations

from fastapi import APIRouter

from ..db import get_collection, reset_database
from ..rebuild import is_rebuilding, is_rebuild_locked

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/stats")
def stats():
    collection = get_collection()
    return {"total_chunks": collection.count()}


@router.post("/reset")
def reset_db():
    reset_database()
    return {"message": "Database reset successfully."}


@router.get("/rebuild/status")
def rebuild_status():
    return {
        "rebuilding": is_rebuilding(),
        "locked": is_rebuild_locked(),
    }
