# RAG Knowledge Assistant

A production-grade Retrieval-Augmented Generation (RAG) system with hybrid retrieval, dual LLM fallback, and a React frontend.

## Features

- **Hybrid Retrieval** — Dense vector search (BAAI/bge-base-en-v1.5 + ChromaDB) fused with sparse BM25 using Reciprocal Rank Fusion (RRF)
- **Dual LLM Fallback** — OpenRouter (primary) → Groq (fallback) with automatic switching
- **Document Ingestion** — PDF upload with PyMuPDF, overlapping chunking, SHA-256 deduplication
- **Audit Logging** — Every retrieval logged to JSONL with scores, chunk IDs, and guard status
- **Hallucination Guard** — Hard block on LLM generation when retrieval confidence is below threshold
- **R2 Storage** — Cloudflare R2 backup for uploaded PDFs (optional)
- **React Frontend** — Clean UI with answer, evidence, sources, and insights panels

## Tech Stack

**Backend:** Python · FastAPI · ChromaDB · Sentence-Transformers · BM25 · OpenRouter · Groq  
**Frontend:** React · Vite · Tailwind CSS  
**Storage:** ChromaDB (vectors) · Cloudflare R2 (PDFs, optional)

## Architecture

## Setup

### Backend

```bash
cd rag--main
cp .env.example .env
# Fill in your API keys in .env
pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8003 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | Yes | App authentication key (any string) |
| `OPENROUTER_API_KEY` | Optional | OpenRouter API key (primary LLM) |
| `OPENROUTER_MODEL` | Optional | Model ID (default: mistralai/mistral-small-24b-instruct-2501) |
| `GROQ_API_KEY` | Optional | Groq API key (fallback LLM) |
| `GROQ_MODEL` | Optional | Groq model (default: llama-3.1-8b-instant) |
| `R2_ENDPOINT_URL` | Optional | Cloudflare R2 endpoint |
| `R2_ACCESS_KEY_ID` | Optional | Cloudflare R2 access key |
| `R2_SECRET_ACCESS_KEY` | Optional | Cloudflare R2 secret |
| `R2_BUCKET_NAME` | Optional | Cloudflare R2 bucket name |
| `EMBEDDING_MODEL` | Optional | Sentence-transformers model (default: BAAI/bge-base-en-v1.5) |
| `CHROMA_PATH` | Optional | ChromaDB persistence path |

## Key Engineering Decisions

- **RRF over weighted sum** — Reciprocal Rank Fusion combines vector and BM25 scores without needing normalization
- **Ingest-before-delete** — New chunks are stored before stale ones are removed, preventing data loss on re-upload
- **Non-fatal R2** — R2 upload failure is a warning, not a crash; ChromaDB is the operational store
- **Thread-safe singletons** — All clients use double-checked locking pattern
- **Audit trail** — Full retrieval audit log enables debugging and quality measurement over time
