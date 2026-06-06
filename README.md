# RAG Knowledge Assistant

A production-ready Retrieval-Augmented Generation system for querying PDF documents. Hybrid BM25 + vector retrieval fused with Reciprocal Rank Fusion, dual LLM fallback (OpenRouter → Groq), SHA-256 content deduplication, Cloudflare R2 backup with cold-start rebuild, and per-query retrieval audit logging.

---

## Architecture

### Ingestion Pipeline

```
Client
  │
  │  POST /upload (multipart/form-data)
  ▼
routes_documents.py
  ├─ Validate: .pdf extension, ≤ MAX_UPLOAD_MB (default 50 MB)
  ├─ Write bytes → OS tempfile
  ├─ create_task(task_id)  ←── persisted to task_state.json immediately
  ├─ Spawn daemon thread
  └─ Return {task_id, status: "pending"}   ←── client polls GET /tasks/{id}

            background thread
                  │
                  ▼
         ingestion_service.py :: run_ingest_task()
          │
          ├─ 1. SHA-256 hash  (streaming 1 MB chunks, no full-file buffer)
          │
          ├─ 2. Dedup check
          │       ChromaDB: GET WHERE content_hash = <hash>
          │       if match → set_task_status("done"), return early
          │
          ├─ 3. R2 upload  (try/except — failure is logged, not re-raised)
          │       boto3.upload_file → R2_BUCKET_NAME / <doc_id>/<filename>
          │
          ├─ 4. ingest_pdf_file_path()   ←── NEW chunks stored first
          │       ├─ PyMuPDF: open PDF, extract text page-by-page
          │       ├─ clean_text(): collapse whitespace, trim 3+ newlines
          │       ├─ chunk_text(size=380, overlap=60) per page
          │       ├─ embed_texts() → BAAI/bge-base-en-v1.5 (normalized L2)
          │       └─ collection.add(ids, chunks, metadatas, embeddings)
          │             metadatas: file, doc_id, page, chunk_index,
          │                        size, uploaded_at, s3_key, content_hash
          │
          ├─ 5. Delete stale chunks (AFTER successful ingest)
          │       collection.delete($and: file=<filename>, doc_id≠<new_doc_id>)
          │       (safe to delete now — new chunks are confirmed stored)
          │
          ├─ 6. warmup_bm25_index()
          │       Re-fetches all docs from ChromaDB, re-tokenizes,
          │       rebuilds BM25Okapi in-process, stores in _bm25_cache
          │
          ├─ 7. set_task_status("done")
          │
          └─ on any exception:
                  delete partial chunks (WHERE doc_id = <new_doc_id>)
                  set_task_status("failed"), set_task_error(str(e))
                  unlink tempfile
```

### Query Pipeline

```
Client
  │
  │  POST /query  {query, top_k=3, document_id?}
  ▼
routes_query.py
  │
  ▼
retrieval.py :: retrieve_chunks()
  │
  ├─ EARLY EXIT: if collection.count() == 0
  │     → guard_fired=True, write audit, return "no_context"
  │
  ├─ KEYWORD EXTRACTION
  │     tokenize query → remove stopwords → normalize variants
  │     (e.g. "colour"→"color", "quantisation"→"quantization")
  │     → expand synonyms (e.g. "sampling"→["sampling","sample"])
  │
  ├─ VECTOR SEARCH
  │     prepend BGE prefix: "Represent this sentence for searching relevant passages: "
  │     BAAI/bge-base-en-v1.5.encode(query) → normalized embedding
  │     ChromaDB.query(top_k=max(5,top_k), where=doc_id?)
  │     distance → score: max(0.0, 1.0 - distance/2)
  │
  ├─ BM25 SEARCH
  │     load _bm25_cache (pre-built at startup / after each ingest)
  │     BM25Okapi.get_scores(query_tokens) → top-5 by raw score
  │     normalize: score / max_bm25_score
  │
  ├─ RRF FUSION (Reciprocal Rank Fusion)
  │     sort candidates by vector_score → get vector_rank
  │     sort candidates by bm25_score → get bm25_rank
  │     rrf_score = 1/(60 + vector_rank) + 1/(60 + bm25_rank)
  │     sort all candidates by rrf_score descending
  │
  ├─ QUALITY FILTERS
  │     - skip chunks < 12 words after cleaning
  │     - strip known title noise phrases
  │     - _is_repetitive_chunk(): reject if any trigram ≥ 30% of all trigrams
  │     - _clean_broken_sentences(): drop fragment sentences < 5 words
  │
  ├─ HALLUCINATION GUARD
  │     if candidates is empty after filters → guard_fired=True, return early
  │
  ├─ AUDIT LOG  (retrieval_audit.jsonl, thread-safe append)
  │     {ts, query_hash, top_scores, num_chunks, doc_ids,
  │      guard_fired, threshold_decision{threshold, reason, gap, spread}}
  │
  └─ return {chunks[:top_k], context, guard_fired=False, status="ok"}

  ▼
llm_router.py → llm.py :: generate_answer()
  │
  ├─ Try OpenRouter (if OPENROUTER_API_KEY present):
  │     POST https://openrouter.ai/api/v1/chat/completions
  │     model: OPENROUTER_MODEL (default: mistralai/mistral-small-24b-instruct-2501)
  │     context capped at 8,000 chars, timeout: 30s
  │     on failure → log warning, fall through to Groq
  │
  └─ Groq fallback (if GROQ_API_KEY present):
        POST https://api.groq.com/openai/v1/chat/completions
        model: GROQ_MODEL (default: llama-3.1-8b-instant)
        max_tokens: 2048, temperature: 0.2
        on failure → return "unable to generate" message

  ▼
{answer, sources, guard_fired, retrieval_score, status}
```

### Cold-Start Rebuild (Stateless Deployments)

```
App startup (daemon thread)
  └─ rebuild_from_r2_if_empty()
        if collection.count() > 0 → skip
        acquire non-blocking _rebuild_lock (one rebuild at a time)
        list_all_pdfs_in_r2() → paginated S3 ListObjectsV2
        for each key:
          download_pdf_from_r2(key, tmpdir/filename)
          ingest_pdf_file_path(...)
        → warmup_bm25_index()
```

---

## Features

- **Hybrid BM25 + vector retrieval** — BM25Okapi keyword search merged with BAAI/bge-base-en-v1.5 cosine similarity, fused via Reciprocal Rank Fusion (RRF, k=60)
- **Hallucination guard** — blocks LLM calls when no candidates survive retrieval; returns a deterministic "no context" response instead of sending empty context to the LLM
- **SHA-256 content deduplication** — streamed hash over raw file bytes; duplicate content rejected before any ChromaDB writes, regardless of filename
- **Dual LLM fallback** — OpenRouter (primary) → Groq (fallback) with automatic switching on failure; no TinyLlama dependency
- **Ingest-before-delete ordering** — new chunks are stored and confirmed before stale chunks from re-uploads are removed; prevents data loss on failed re-ingestion
- **Async upload with task polling** — `POST /upload` returns a `task_id` immediately; ingestion runs in a daemon thread; state polled via `GET /tasks/{task_id}`
- **Non-fatal Cloudflare R2 backup** — PDFs uploaded to R2 after hash check; R2 errors caught and logged but never fail the ingestion task
- **Cold-start rebuild** — on startup, if ChromaDB is empty and R2 is configured, all PDFs re-downloaded and re-ingested automatically
- **Thread-safe singletons** — ChromaDB client, embedding model, BM25 cache each use double-checked locking
- **ChromaDB embedding model migration** — on startup, if stored collection's `embedding_model` metadata differs from configured model, all documents are re-embedded
- **Per-query retrieval audit log** — every query writes a JSONL line to `retrieval_audit.jsonl` with timestamp, query hash, top scores, chunk count, doc IDs, guard status, and adaptive threshold decision
- **Adaptive score thresholds** — `_threshold_decision()` adjusts the no-context threshold ±0.08 based on score gap and spread
- **Keyword normalization + synonym expansion** — British spellings normalized, domain synonyms expanded, stopwords stripped before BM25 tokenization
- **Atomic task state persistence** — task dict written via `.tmp` rename to `task_state.json`; in-flight tasks marked failed on restart
- **Rollback on ingestion failure** — chunks written under new `doc_id` deleted before task marked failed
- **Page-tracked chunks** — each chunk metadata carries source page number for per-page citation in frontend
- **BGE query prefix** — vector queries prefixed per BGE model's retrieval instruction convention
- **R2 file cleanup on delete** — when a document is deleted via API, its R2 PDF is also deleted (non-fatal if R2 not configured)

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| API server | FastAPI | ≥ 0.115.0 |
| ASGI runtime | Uvicorn | ≥ 0.30.0 |
| Vector store | ChromaDB (PersistentClient) | ≥ 0.5.5 |
| Embedding model | BAAI/bge-base-en-v1.5 (SentenceTransformer) | ≥ 3.0.1 |
| Keyword retrieval | BM25Okapi (rank-bm25) | ≥ 0.2.2 |
| PDF extraction | PyMuPDF (fitz) | ≥ 1.24.9 |
| Primary LLM | OpenRouter API | — |
| Fallback LLM | Groq API | — |
| Object storage | Cloudflare R2 (boto3 S3-compatible) | ≥ 1.34.0 |
| Data validation | Pydantic v2 | ≥ 2.7.0 |
| Frontend | React 19 + Vite + Tailwind CSS 3 | — |
| Animations | Framer Motion | ≥ 12 |
| HTTP client | Axios | ≥ 1.15.0 |

---

## Project Structure

```
rag--main/
├── backend/
│   ├── app.py                      # FastAPI app, CORS, startup hooks
│   ├── config.py                   # CORS origins, upload size limit
│   ├── db.py                       # ChromaDB singleton, embed, CRUD, migration
│   ├── ingestion.py                # PDF extraction + chunk-embed-store pipeline
│   ├── retrieval.py                # Hybrid retrieval: vector + BM25 + RRF + guard
│   ├── llm.py                      # OpenRouter + Groq dual LLM with fallback
│   ├── llm_router.py               # Thin router: generate_answer(query, context)
│   ├── storage.py                  # Cloudflare R2 client (thread-safe singleton)
│   ├── tasks.py                    # In-process task registry + JSON persistence
│   ├── utils.py                    # chunk_text, clean_text
│   ├── rebuild.py                  # Cold-start R2 → ChromaDB rebuild
│   ├── api/
│   │   ├── routes_documents.py     # POST /upload, GET /documents, DELETE /documents/{id}
│   │   ├── routes_query.py         # POST /query
│   │   └── routes_core.py          # GET /health, GET /tasks/{id}
│   └── services/
│       ├── ingestion_service.py    # Full ingestion orchestration (hash, R2, ingest, BM25)
│       └── rebuild_service.py      # R2 listing + re-ingestion logic
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── components/             # ChatBox, DocumentList, FileUpload, MessageBubble,
│       │                           # QueryInput, Sidebar, SourcesPanel, EvidencePanel
│       ├── pages/
│       │   └── Dashboard.jsx
│       └── services/
│           └── api.js
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Groq API key (free at console.groq.com) OR OpenRouter API key

### Backend

```bash
git clone https://github.com/rudranaresh0201/rag-
cd rag--main
cp .env.example .env
# Fill in your API keys — minimum: GROQ_API_KEY and API_KEY
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

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | Yes | App auth key (any string you choose) |
| `USE_OPENROUTER` | Optional | Set `true` to use OpenRouter as primary LLM |
| `OPENROUTER_API_KEY` | Optional | OpenRouter API key |
| `OPENROUTER_MODEL` | Optional | Default: `mistralai/mistral-small-24b-instruct-2501` |
| `GROQ_API_KEY` | Optional | Groq API key (fallback LLM, free tier available) |
| `GROQ_MODEL` | Optional | Default: `llama-3.1-8b-instant` |
| `EMBEDDING_MODEL` | Optional | Default: `BAAI/bge-base-en-v1.5` |
| `CHROMA_PATH` | Optional | ChromaDB persistence path (default: `./chroma_db`) |
| `HF_CACHE_DIR` | Optional | HuggingFace model cache directory |
| `MAX_UPLOAD_MB` | Optional | Max PDF upload size in MB (default: `50`) |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins |
| `NO_CONTEXT_THRESHOLD` | Optional | Hallucination guard threshold (default: `0.3`) |
| `LLM_MAX_TIME_SECONDS` | Optional | LLM timeout in seconds (default: `20`) |
| `FAST_MODE` | Optional | Skip slow post-processing (default: `true`) |
| `R2_ENDPOINT_URL` | Optional | Cloudflare R2 endpoint URL |
| `R2_ACCESS_KEY_ID` | Optional | Cloudflare R2 access key |
| `R2_SECRET_ACCESS_KEY` | Optional | Cloudflare R2 secret key |
| `R2_BUCKET_NAME` | Optional | Cloudflare R2 bucket name |
| `CROSS_ENCODER_MODEL` | Optional | Planned reranker (not yet active in pipeline) |

---

## API Reference

### `POST /upload`
Upload a PDF for ingestion.

**Request:** `multipart/form-data` — field `file` (.pdf, ≤ MAX_UPLOAD_MB)

**Response `200`:**
```json
{"task_id": "uuid", "status": "pending"}
```

**Errors:** `400` bad extension · `413` file too large

---

### `GET /tasks/{task_id}`
Poll ingestion task status.

**Response `200`:**
```json
{
  "task_id": "uuid",
  "status": "pending | processing | done | failed",
  "error": null
}
```

---

### `GET /documents`
List all ingested documents.

**Response `200`:**
```json
[
  {
    "doc_id": "abc123",
    "file": "report.pdf",
    "page_count": 12,
    "chunk_count": 48,
    "uploaded_at": "2026-06-01T12:00:00Z",
    "s3_key": "abc123/report.pdf"
  }
]
```

---

### `DELETE /documents/{doc_id}`
Delete a document and its chunks. Also deletes the PDF from R2 (non-fatal if R2 not configured).

**Response `200`:**
```json
{"message": "Document abc123 deleted."}
```

---

### `POST /query`
Query documents using hybrid retrieval + LLM.

**Request body:**
```json
{
  "query": "What is the refund policy?",
  "top_k": 3,
  "document_id": null
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | The question to ask |
| `top_k` | integer | `3` | Number of chunks to retrieve |
| `document_id` | string \| null | `null` | Scope to single document; null = all documents |

**Response `200` — context found:**
```json
{
  "answer": "The refund policy states...",
  "sources": [
    {
      "text": "Refunds are processed within 30 days...",
      "file": "policy.pdf",
      "doc_id": "abc123",
      "page": 4,
      "metadata": {
        "file": "policy.pdf",
        "doc_id": "abc123",
        "page": 4,
        "chunk_index": 2,
        "uploaded_at": "2026-06-01T12:00:00Z",
        "s3_key": "abc123/policy.pdf",
        "content_hash": "e3b0c44..."
      }
    }
  ],
  "guard_fired": false,
  "retrieval_score": null,
  "status": "ok"
}
```

**Response `200` — hallucination guard fired:**
```json
{
  "answer": "I cannot find relevant information for this query in the provided documents.",
  "sources": [],
  "guard_fired": true,
  "retrieval_score": null,
  "status": "no_context"
}
```

**Errors:** `400` empty query

---

### `GET /health`
Health check.

**Response `200`:** `{"status": "ok"}`

---

## Key Engineering Decisions

### RRF over weighted score fusion
Vector scores (cosine, 0–1) and BM25 scores (unbounded floats) cannot be combined by addition without normalization. RRF uses rank position instead of score magnitude — `1/(60 + rank)` — so the two signals fuse correctly regardless of their original scale. This is the same algorithm used in production by Elasticsearch and Weaviate.

### Ingest-before-delete for re-uploads
The naive ordering deletes stale chunks before ingesting new ones. If ingestion then fails, the old chunks are gone and the rollback only clears the new (also failed) doc_id — the document disappears from the system entirely. The correct ordering stores new chunks first, verifies success, then deletes stale chunks under a compound `$and` filter targeting only chunks from previous versions of the same filename.

### Non-fatal R2 upload
R2 is a backup for cold-start recovery on ephemeral deployments, not the primary store. ChromaDB is the live query target. Refusing to ingest when R2 is unreachable would lose the user's document from the system entirely — the wrong tradeoff. R2 failure is caught, logged as a warning, and ingestion continues.

### Double-checked locking for all singletons
`get_client()`, `get_embedder()`, `get_collection()`, and the BM25 cache all use the same pattern: check the global without the lock (fast path for 99.9% of calls after warmup), acquire the lock, check again. The second check prevents a second thread that passed the first check from re-initializing. Without this, concurrent startup requests could trigger multiple simultaneous embedding model loads.

### SHA-256 for deduplication instead of filename
Filename-based dedup prevents correcting a document: re-uploading `report_v2.pdf` as `report.pdf` would be accepted because the filename differs. SHA-256 over raw bytes rejects only bit-identical files. Two files with the same name but different content produce different hashes and both proceed — the stale-chunk delete handles the version replacement.

### Hallucination guard at the retrieval boundary
Rather than sending empty context to the LLM and relying on prompt instructions to refuse correctly, the guard short-circuits before the LLM is called when no candidates survive retrieval. This eliminates hallucinations caused by a compliant LLM attempting to answer with no relevant material — a class that prompt-only mitigations handle unreliably.

### Adaptive score thresholds
`_threshold_decision()` inspects the top-5 retrieval scores before applying the guard. A large gap between top-1 and top-2 (≥ 0.25) means one chunk is clearly the best match — threshold is lowered by 0.08. Tightly clustered scores (gap ≤ 0.05) indicate ambiguity — threshold raised by 0.08. This produces more stable recall than a fixed threshold across corpora with varying document density.

### Dual LLM with Groq fallback
OpenRouter provides access to many models but has occasional cold-start latency and model availability issues. Groq provides near-instant inference on Llama models with a generous free tier. The system tries OpenRouter first, logs the full response body on failure, and falls through to Groq automatically — no manual intervention required.

---

## Known Limitations

**BM25 index rebuilt in full after every ingestion.** The entire ChromaDB corpus is fetched, re-tokenized, and re-indexed as a new `BM25Okapi` object in memory after each upload. On large corpora this takes seconds and queries during the rebuild window use a stale cache.

**No authentication enforced.** `API_KEY` is defined in `.env.example` but not enforced by any middleware. All endpoints are publicly accessible to anyone who can reach the server.

**No streaming responses.** `POST /query` blocks until LLM generation completes. Add an SSE endpoint for production deployments with slow LLM providers.

**R2 rebuild does not preserve doc_id.** `rebuild_from_r2_if_empty` assigns new UUIDs on every cold-start rebuild. Client-side references to `doc_id` will break after a rebuild.

**Chunk size is character-based not token-based.** `chunk_text(size=380, overlap=60)` splits on character count. On dense technical text, 380 characters can be as few as 50–60 tokens — potentially too small for complex multi-sentence context.

**Single-collection ChromaDB.** All documents share one collection (`rag_documents`). There is no per-user or per-project isolation at the vector store level.

**`CROSS_ENCODER_MODEL` is not active.** The env var appears in `.env.example` and the model name is referenced but no reranking step is wired into the retrieval pipeline. Placeholder for a planned cross-encoder stage.

**Task store is in-memory per process.** With multiple uvicorn workers, task IDs from one worker are invisible to others. Use Redis or a proper task queue (Celery, ARQ) for multi-worker deployments.
