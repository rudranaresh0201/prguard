# Agentic RAG — LangGraph Multi-Agent Document Intelligence

A production-grade RAG system upgraded with a LangGraph multi-agent orchestration layer. Queries are routed intelligently across internal documents, live web search, or both — then synthesised into a single comprehensive answer.

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    Router Agent                          │
│  Classifies query → rag | web | both | unclear          │
└──────────────┬──────────────────────┬───────────────────┘
               │                      │
        ┌──────▼──────┐        ┌──────▼──────┐
        │  RAG Agent  │        │  Web Agent  │
        │  BM25 +     │        │  Tavily     │
        │  Vector     │        │  live search│
        │  Hybrid RRF │        └──────┬──────┘
        └──────┬──────┘               │
               └──────────┬───────────┘
                           │
                    ┌──────▼──────────┐
                    │ Synthesis Agent │
                    │ Lists ALL items │
                    │ never truncates │
                    └──────┬──────────┘
                           │
                    ┌──────▼──────┐
                    │  Response   │
                    │ answer +    │
                    │ sources +   │
                    │ route/steps │
                    └─────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph, LangChain-Groq |
| LLM (router + synthesis) | Groq `llama-3.1-8b-instant` (configurable) |
| LLM fallback (synthesis) | OpenRouter (configurable model) |
| Web search | Tavily |
| Backend API | FastAPI |
| Vector store | ChromaDB |
| Embeddings | Sentence-Transformers |
| Sparse retrieval | BM25 (Okapi) |
| Retrieval fusion | Reciprocal Rank Fusion (RRF) |
| Frontend | React + Vite |

---

## Agent Endpoints

### `POST /agent/query`

Runs the full LangGraph pipeline and returns a complete answer.

**Request:**
```bash
curl -X POST http://localhost:8003/agent/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 12345" \
  -d '{"query": "What internships has Rudra done?"}'
```

**Response:**
```json
{
  "answer": "Rudra has completed two internships:\n- OpenRAG (Remote Backend Engineering Intern, 2026-Present): Built a production-grade multi-agent CSV/XLSX analytics system for DocDynamo using 7 specialist CrewAI agents.\n- 4seer Technologies (Remote Software Engineering Intern, 2026-Present): Building a FastAPI microservice for automated PDF generation for the Amplex project.",
  "route": "rag",
  "steps": [
    "Router → rag",
    "RAG → 8 chunks retrieved",
    "Synthesis complete"
  ],
  "rag_sources": [
    "Rudra_Naresh_resume (1).pdf",
    "Rudra_Naresh_resume (1).pdf"
  ],
  "web_sources": []
}
```

---

### `POST /agent/query/stream`

Server-Sent Events stream. Emits agent step events as they happen, then a final `done` event.

```bash
curl -X POST http://localhost:8003/agent/query/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 12345" \
  -d '{"query": "Latest AI news"}' \
  --no-buffer
```

**Event stream:**
```
data: {"type": "step", "node": "router"}
data: {"type": "step", "node": "web"}
data: {"type": "token", "content": "Here are the latest"}
data: {"type": "token", "content": " AI developments..."}
data: {"type": "done", "route": "web", "steps": [...]}
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the required keys.

### Required

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key — used by router, RAG rewriter, and synthesis agents |
| `TAVILY_API_KEY` | Tavily API key — used by the web search agent |

### Optional — LLM

| Variable | Default | Description |
|---|---|---|
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model for all agent nodes |
| `OPENROUTER_API_KEY` | — | If set, synthesis uses OpenRouter first (Groq is fallback) |
| `OPENROUTER_MODEL` | `mistralai/mistral-small-24b-instruct-2501` | OpenRouter model |

### Optional — RAG / Retrieval

| Variable | Default | Description |
|---|---|---|
| `RAG_TOP_K` | `8` | Number of chunks retrieved per query |
| `RAG_CHUNK_SIZE` | `1200` | Max characters per chunk (sentence-boundary aware) |
| `RAG_CHUNK_OVERLAP` | `100` | Overlap between chunks in characters |
| `RAG_RERANK_WINDOW` | `500` | Window size for BM25 re-ranking pass |
| `RAG_RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `AGENT_WEB_RESULTS` | `5` | Number of Tavily web results per query |

### Optional — Server

| Variable | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `50` | Maximum PDF upload size |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS allowed origins (comma-separated) |

---

## Setup

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add GROQ_API_KEY and TAVILY_API_KEY

# Start the server
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8003 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## Project Structure

```
backend/
├── agent/
│   ├── graph.py          # LangGraph state machine definition
│   ├── nodes.py          # Router, RAG, Web, Synthesis, Clarify nodes
│   └── state.py          # AgentState TypedDict
├── api/
│   ├── routes_agent.py   # /agent/query and /agent/query/stream
│   ├── routes_core.py    # /health, /reset
│   ├── routes_documents.py
│   └── routes_query.py   # Legacy /query endpoint
├── config.py             # All env-overridable constants
├── ingestion.py          # PDF to sentence-aware chunks to ChromaDB
├── llm.py                # OpenRouter to Groq fallback chain
├── retrieval.py          # Hybrid BM25 + vector + RRF fusion
└── utils.py              # chunk_text (sentence-boundary), clean_text

frontend/src/
├── pages/Dashboard.jsx
├── components/
└── services/api.js       # queryApi / queryRagByDocument -> /agent/query
```
