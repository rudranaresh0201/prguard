from __future__ import annotations

from datetime import datetime, timezone
import uuid
from pathlib import Path
from typing import TypedDict

try:
    import fitz
except ImportError:
    fitz = None

from .db import embed_texts, get_collection
from .config import RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP
from .utils import chunk_text, clean_text

from .core.logging import get_logger

logger = get_logger(__name__)


class InvalidPDFError(Exception):
    pass


class MissingDependencyError(Exception):
    pass


class IngestionResult(TypedDict):
    chunks: int
    doc_id: str
    filename: str
    size: int
    uploaded_at: str


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if fitz is None:
        raise MissingDependencyError("PyMuPDF not installed. Run: pip install pymupdf")

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            pages = [page.get_text("text") for page in doc]
            logger.info("[PDF] Opened from bytes: page_count=%d", page_count)
    except Exception as exc:
        logger.error("[PDF] Failed to open PDF from bytes: %s", exc)
        raise InvalidPDFError("Invalid or unreadable PDF.") from exc

    text = "\n".join(pages)
    cleaned = clean_text(text)
    logger.info(
        "[PDF] Extracted text from bytes: raw_chars=%d cleaned_chars=%d",
        len(text), len(cleaned),
    )
    return cleaned


def extract_text_from_pdf_path(pdf_path: str) -> str:
    if fitz is None:
        raise MissingDependencyError("PyMuPDF not installed. Run: pip install pymupdf")

    try:
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
            pages = [page.get_text("text") for page in doc]
            logger.info("[PDF] Opened from path=%s page_count=%d", pdf_path, page_count)
    except Exception as exc:
        logger.error("[PDF] Failed to open PDF path=%s: %s", pdf_path, exc)
        raise InvalidPDFError("Invalid or unreadable PDF.") from exc

    text = "\n".join(pages)
    cleaned = clean_text(text)
    logger.info(
        "[PDF] Extracted text from path=%s raw_chars=%d cleaned_chars=%d",
        pdf_path, len(text), len(cleaned),
    )
    return cleaned


def ingest_pdf(
    pdf_bytes: bytes,
    filename: str,
    file_size: int,
    doc_id: str | None = None,
    s3_key: str | None = None,
    file_hash: str | None = None,
) -> IngestionResult:
    logger.info("Starting PDF ingestion filename=%s size=%s", filename, file_size)
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        raise InvalidPDFError("PDF has no extractable text.")

    # Chunk per page and track page numbers
    chunks = []
    chunk_pages = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc, start=1):
            raw_page_text = page.get_text("text")
            # Fix PDF line breaks before chunking
            page_text = raw_page_text.replace("-\n", "").replace("\n", " ")
            page_text = " ".join(page_text.split())
            page_text = clean_text(page_text)
            if not page_text.strip():
                continue
            page_chunks = chunk_text(
                text=page_text,
                chunk_size=RAG_CHUNK_SIZE,
                overlap=RAG_CHUNK_OVERLAP
            )
            for chunk in page_chunks:
                if chunk.strip():
                    chunks.append(chunk.strip())
                    chunk_pages.append(page_num)

    if not chunks:
        raise InvalidPDFError("No valid text chunks were produced.")

    embeddings = embed_texts(chunks)
    doc_id = str(doc_id or uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()
    ids = [f"{Path(filename).stem}-{uuid.uuid4()}" for _ in chunks]
    metadatas = [
        {
            "file": filename,
            "doc_id": doc_id,
            "size": int(file_size),
            "uploaded_at": uploaded_at,
            "chunk_index": index,
            "page": chunk_pages[index],
            "s3_key": s3_key or "",
            "content_hash": file_hash or "",
        }
        for index in range(len(chunks))
    ]
    collection = get_collection()
    collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
    logger.info("CHUNKS STORED: %s", len(chunks))
    logger.info("TOTAL IN DB: %s", collection.count())
    logger.info(
        "Completed PDF ingestion filename=%s size=%s chunks=%s doc_id=%s",
        filename,
        file_size,
        len(chunks),
        doc_id,
    )

    return {
        "chunks": len(chunks),
        "doc_id": doc_id,
        "filename": filename,
        "size": int(file_size),
        "uploaded_at": uploaded_at,
    }


def ingest_pdf_file_path(
    pdf_path: str,
    filename: str,
    file_size: int,
    doc_id: str | None = None,
    s3_key: str | None = None,
    file_hash: str | None = None,
) -> IngestionResult:
    logger.info("[INGEST] Starting ingestion filename=%s size_bytes=%d", filename, file_size)

    # ---- TEXT EXTRACTION ----
    text = extract_text_from_pdf_path(pdf_path)
    if not text:
        logger.error("[INGEST] Empty extracted text filename=%s — possibly a scanned/image PDF", filename)
        raise InvalidPDFError("PDF has no extractable text.")
    logger.info("[INGEST] Extracted text length=%d chars filename=%s", len(text), filename)

    # ---- CHUNKING WITH PAGE TRACKING ----
    chunks = []
    chunk_pages = []
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            raw_page_text = page.get_text("text")
            # Fix PDF line breaks before chunking
            page_text = raw_page_text.replace("-\n", "").replace("\n", " ")
            page_text = " ".join(page_text.split())
            page_text = clean_text(page_text)
            if not page_text.strip():
                continue
            page_chunks = chunk_text(
                text=page_text,
                chunk_size=RAG_CHUNK_SIZE,
                overlap=RAG_CHUNK_OVERLAP
            )
            for chunk in page_chunks:
                if chunk.strip():
                    chunks.append(chunk.strip())
                    chunk_pages.append(page_num)
    if not chunks:
        logger.error("[INGEST] Zero valid chunks produced filename=%s", filename)
        raise InvalidPDFError("No valid text chunks were produced.")
    logger.info("[INGEST] Chunks produced: count=%d filename=%s", len(chunks), filename)

    # ---- EMBEDDINGS ----
    logger.info("[INGEST] Generating embeddings for %d chunks filename=%s", len(chunks), filename)
    embeddings = embed_texts(chunks)
    if not embeddings:
        logger.error("[INGEST] Embedding generation returned empty list filename=%s", filename)
        raise RuntimeError("Embedding generation failed — empty result.")
    emb_dim = len(embeddings[0]) if embeddings else 0
    logger.info(
        "[INGEST] Embeddings generated: count=%d dimensions=%d filename=%s",
        len(embeddings), emb_dim, filename,
    )

    # ---- METADATA ----
    doc_id = str(doc_id or uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()
    ids = [f"{Path(filename).stem}-{uuid.uuid4()}" for _ in chunks]
    metadatas = [
        {
            "file": filename,
            "doc_id": doc_id,
            "size": int(file_size),
            "uploaded_at": uploaded_at,
            "chunk_index": index,
            "page": chunk_pages[index],
            "s3_key": s3_key or "",
            "content_hash": file_hash or "",
        }
        for index in range(len(chunks))
    ]

    # ---- CHROMADB INSERT ----
    logger.info("[INGEST] Inserting %d chunks into ChromaDB filename=%s doc_id=%s", len(chunks), filename, doc_id)
    collection = get_collection()
    collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
    total_in_db = collection.count()
    logger.info(
        "[INGEST] DB insertion confirmed: stored=%d total_in_db=%d filename=%s doc_id=%s",
        len(chunks), total_in_db, filename, doc_id,
    )

    return {
        "chunks": len(chunks),
        "doc_id": doc_id,
        "filename": filename,
        "size": int(file_size),
        "uploaded_at": uploaded_at,
    }
