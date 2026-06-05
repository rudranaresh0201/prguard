# RAGnosis 🧠

A full-stack RAG (Retrieval-Augmented Generation) system that lets users upload PDFs and ask questions with structured, evidence-backed answers.

## Live Demo
- **App**: https://rudra0201-rudranaresh-frontend.hf.space
- **API Docs**: https://rudra0201-rudranaresh.hf.space/docs

## Tech Stack
- **Frontend**: React + Vite + TailwindCSS
- **Backend**: FastAPI + ChromaDB + SentenceTransformers
- **LLM**: OpenRouter (free tier)
- **Hosting**: HuggingFace Spaces

## Features
- Upload PDFs and ask questions
- Structured answers with Summary, Key Points, Explanation
- Source citations with confidence scores
- Evidence-backed responses

## Local Setup
\\ash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload
\