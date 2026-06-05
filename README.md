# RAGnosis — Ask With Evidence, Think With Structure

A production-grade Hybrid Retrieval-Augmented Generation (RAG) system 
with multi-document querying, cross-encoder reranking, and structured 
LLM responses.

## Features

- Hybrid retrieval (Dense Vector + BM25 keyword search)
- Cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
- BGE embeddings with asymmetric query prefix
- Page-level source citations
- Structured responses (Summary, Key Points, Explanation)
- Multi-document PDF querying with document isolation
- Async ingestion pipeline with task polling
- OpenRouter LLM routing (Llama 3.1 / configurable)
- Confidence threshold gate (prevents hallucination on weak context)

## Tech Stack

- **Frontend:** React (Vite)
- **Backend:** FastAPI (async)
- **Vector DB:** ChromaDB (persistent)
- **Embeddings:** BAAI/bge-base-en-v1.5 (Sentence Transformers)
- **Sparse Retrieval:** BM25 (rank-bm25)
- **Reranking:** Cross-encoder (ms-marco-MiniLM-L-6-v2)
- **LLM:** Llama 3.1 8B via OpenRouter

## Architecture  ## How to Run

```bash
# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env  # fill in your OPENROUTER_API_KEY
uvicorn backend.app:app --reload --port 8004

# Frontend
cd frontend
npm install
npm run dev
```

## Environment Variables## Live Demo

[Live Demo on HuggingFace Spaces](https://huggingface.co/spaces/rudra0201/rudranaresh-frontend)
