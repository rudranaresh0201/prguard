from __future__ import annotations

import os


def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_max_upload_bytes() -> int:
    try:
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    except ValueError:
        max_mb = 50
    return max(1, max_mb) * 1024 * 1024


# ── RAG Retrieval ──────────────────────────────────────────
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1200"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
RAG_RERANK_WINDOW = int(os.getenv("RAG_RERANK_WINDOW", "500"))
RAG_RRF_K = int(os.getenv("RAG_RRF_K", "60"))

# ── Agent / LLM ────────────────────────────────────────────
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
AGENT_WEB_RESULTS = int(os.getenv("AGENT_WEB_RESULTS", "5"))
