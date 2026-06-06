from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Dict, List

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from .core.logging import get_logger

BASE_DIR = Path(__file__).resolve().parent
_chroma_path_env = os.getenv("CHROMA_PATH", "").strip()
if _chroma_path_env:
    # Resolve relative paths from BASE_DIR so the location is server-start-directory-agnostic
    _chroma_path_candidate = Path(_chroma_path_env)
    if not _chroma_path_candidate.is_absolute():
        _chroma_path_candidate = BASE_DIR.parent / _chroma_path_candidate
    CHROMA_PATH = str(_chroma_path_candidate.resolve())
else:
    CHROMA_PATH = str((BASE_DIR / "chroma_db").resolve())
COLLECTION_NAME = "rag_documents"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

_client = None
_embedder: SentenceTransformer | None = None
_collection_verified = False
_client_lock = threading.Lock()
_embedder_lock = threading.Lock()
_collection_verify_lock = threading.Lock()

logger = get_logger(__name__)


def get_client():
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        db_dir = Path(CHROMA_PATH).resolve()
        db_dir.mkdir(parents=True, exist_ok=True)

        try:
            _client = chromadb.PersistentClient(
                path=str(db_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                ),
            )
            # Touch collection metadata once to fail fast on corruption.
            _client.get_or_create_collection(name=COLLECTION_NAME)
        except Exception:
            _client = None
            try:
                shutil.rmtree(db_dir, ignore_errors=True)
            except Exception:
                pass
            db_dir.mkdir(parents=True, exist_ok=True)

            _client = chromadb.PersistentClient(
                path=str(db_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                ),
            )
            _client.get_or_create_collection(name=COLLECTION_NAME)

    return _client


def get_collection() -> Collection:
    global _collection_verified
    client = get_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"embedding_model": EMBEDDING_MODEL_NAME},
    )

    if _collection_verified:
        return collection

    with _collection_verify_lock:
        # Re-check after acquiring the lock to avoid duplicate migration.
        if _collection_verified:
            return collection

        current_metadata = collection.metadata or {}
        current_model = str(current_metadata.get("embedding_model", "")).strip()

        if current_model == EMBEDDING_MODEL_NAME:
            _collection_verified = True
            return collection

        records = collection.get(include=["documents", "metadatas"])
        ids = [str(item) for item in (records.get("ids") or [])]
        documents = [str(item or "") for item in (records.get("documents") or [])]
        metadatas = records.get("metadatas") or []

        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"embedding_model": EMBEDDING_MODEL_NAME},
        )

        valid_rows = [
            (id_value, doc_value, metadata)
            for id_value, doc_value, metadata in zip(ids, documents, metadatas)
            if id_value and doc_value
        ]
        if valid_rows:
            migrated_ids = [row[0] for row in valid_rows]
            migrated_docs = [row[1] for row in valid_rows]
            migrated_metas = [row[2] if isinstance(row[2], dict) else {} for row in valid_rows]
            migrated_embeddings = embed_texts(migrated_docs)
            collection.add(
                ids=migrated_ids,
                documents=migrated_docs,
                metadatas=migrated_metas,
                embeddings=migrated_embeddings,
            )

        _collection_verified = True
    return collection


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedder


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        logger.warning("[EMBED] embed_texts called with empty list")
        return []
    model = get_embedder()
    logger.debug("[EMBED] Encoding %d texts with model=%s", len(texts), EMBEDDING_MODEL_NAME)
    vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    result = vectors.tolist()
    dim = len(result[0]) if result else 0
    logger.info("[EMBED] Embeddings ready: count=%d dimensions=%d", len(result), dim)
    return result


def add_chunks(
    ids: List[str],
    chunks: List[str],
    metadatas: List[Dict[str, str | int]],
    embeddings: List[List[float]],
) -> None:
    collection = get_collection()
    collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)


def query_chunks(
    query_embedding: List[float],
    top_k: int,
    document_id: str | None = None,
) -> Dict:
    collection = get_collection()
    where = {"doc_id": document_id} if document_id else None
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


def get_all_records():
    collection = get_collection()
    try:
        data = collection.get()
        return data
    except Exception as e:
        logger.warning("[DB] get_all_records failed (empty or new collection): %s", e)
        return {"ids": [], "documents": [], "metadatas": []}


def delete_document(document_id: str) -> None:
    collection = get_collection()
    collection.delete(where={"doc_id": document_id})


def get_s3_key_for_document(document_id: str) -> str | None:
    """Return the R2 s3_key for a document before deleting it, or None if not found."""
    collection = get_collection()
    try:
        records = collection.get(
            where={"doc_id": document_id},
            include=["metadatas"],
            limit=1,
        )
        metadatas = records.get("metadatas") or []
        if metadatas and isinstance(metadatas[0], dict):
            key = metadatas[0].get("s3_key", "")
            return str(key) if key else None
    except Exception:
        pass
    return None


def reset_database() -> None:
    global _collection_verified
    client = get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"embedding_model": EMBEDDING_MODEL_NAME},
    )
    _collection_verified = False
