from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, List, TypedDict

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from .core.logging import get_logger
from .config import RAG_RERANK_WINDOW, RAG_RRF_K, RAG_CHUNK_OVERLAP
from .db import get_collection, get_embedder
from .utils import chunk_text as _chunk_text_util

_bm25_cache: dict[str, Any] | None = None
_bm25_lock = threading.Lock()
_audit_lock = threading.Lock()
AUDIT_LOG_PATH = Path(os.getenv("RETRIEVAL_AUDIT_PATH", Path(__file__).resolve().parent / "retrieval_audit.jsonl"))
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do", "does",
    "for", "from", "how", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of", "on",
    "or", "our", "please", "show", "tell", "that", "the", "their", "them", "there", "these", "they",
    "this", "to", "us", "was", "we", "what", "when", "where", "which", "who", "why", "with", "would",
    "you", "your", "explain", "describe", "give", "about",
}
KEYWORD_VARIANTS = {
    "quantisation": "quantization",
    "colour": "color",
    "behaviour": "behavior",
}
KEYWORD_SYNONYMS = {
    "sampling": ["sampling", "sample"],
    "quantization": ["quantization", "quantisation"],
    "encoding": ["encoding", "encode"],
}
NON_CONTENT_QUERY_WORDS = {
    "what", "is", "the", "explain", "story", "describe", "moral",
}
TITLE_NOISE_PHRASES = {
    "design and operation of a modern smart city infrastructure",
    "smart city infrastructure report",
    "technical reference document",
}
try:
    NO_CONTEXT_THRESHOLD = float(os.getenv("NO_CONTEXT_THRESHOLD", "0.3"))
except ValueError:
    NO_CONTEXT_THRESHOLD = 0.3
logger = get_logger(__name__)


class RetrievedChunk(TypedDict):
    text: str
    file: str
    doc_id: str
    page: int | None
    metadata: dict[str, Any]


class RetrievalResult(TypedDict):
    chunks: List[RetrievedChunk]
    context: str
    guard_fired: bool
    retrieval_score: float | None
    status: str


def _normalize_keyword_token(token: str) -> str:
    base = str(token or "").lower().strip()
    return KEYWORD_VARIANTS.get(base, base)


def _expand_keywords(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        normalized = _normalize_keyword_token(token)
        if normalized and normalized not in seen:
            seen.add(normalized)
            expanded.append(normalized)

        synonym_candidates = KEYWORD_SYNONYMS.get(normalized, [normalized])
        for synonym in synonym_candidates:
            normalized_syn = _normalize_keyword_token(synonym)
            if normalized_syn and normalized_syn not in seen:
                seen.add(normalized_syn)
                expanded.append(normalized_syn)

    return expanded


def _extract_query_keywords(query: str) -> list[str]:
    raw_query = str(query or "")
    base_tokens = [
        _normalize_keyword_token(token)
        for token in re.findall(r"[a-zA-Z0-9]+", raw_query.lower())
        if (
            len(token) >= 3
            and _normalize_keyword_token(token) not in STOPWORDS
            and _normalize_keyword_token(token) not in NON_CONTENT_QUERY_WORDS
        )
    ]
    return _expand_keywords(list(dict.fromkeys(base_tokens)))


def _normalize_chunk_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _is_repetitive_chunk(text: str) -> bool:
    tokens = re.findall(r"[a-zA-Z0-9]+", str(text or "").lower())
    if len(tokens) < 24:
        return False

    # Detect repeated phrase domination (e.g., repeated header/title lines).
    trigrams = [" ".join(tokens[i : i + 3]) for i in range(0, len(tokens) - 2)]
    if not trigrams:
        return False
    counts: dict[str, int] = {}
    for phrase in trigrams:
        counts[phrase] = counts.get(phrase, 0) + 1
    max_repeat = max(counts.values()) if counts else 0
    return max_repeat >= 3 and (float(max_repeat) / float(max(1, len(trigrams)))) >= 0.30


def _clean_broken_sentences(text: str) -> str:
    normalized = _normalize_chunk_text(text)
    if not normalized:
        return ""

    segments = re.split(r"(?<=[.!?])\s+", normalized)
    cleaned_segments: list[str] = []
    for segment in segments:
        candidate = segment.strip()
        if not candidate:
            continue

        words = re.findall(r"[a-zA-Z0-9=()+\-/*^.]+", candidate)
        if len(words) < 5 and not any(token in candidate for token in ["=", "defined as", "is given by"]):
            continue

        cleaned_segments.append(candidate)

    return " ".join(cleaned_segments) if cleaned_segments else normalized


def _tokenize(text: str) -> set[str]:
    return {
        _normalize_keyword_token(token)
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 2
    }


def _keyword_query_tokens(query: str) -> list[str]:
    keywords = _extract_query_keywords(query)
    if keywords:
        return keywords
    return [token for token in re.findall(r"[a-zA-Z0-9]+", str(query or "").lower()) if len(token) >= 3]
def _is_near_duplicate(text_a: str, text_b: str, threshold: float = 0.85) -> bool:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return False

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return False

    similarity = float(intersection) / float(union)
    return similarity >= threshold


def _get_embed_model() -> SentenceTransformer:
    # Reuse the single global embedder managed by db.py.
    return get_embedder()


def _threshold_decision(scores: list[float]) -> dict[str, Any]:
    base_threshold = float(NO_CONTEXT_THRESHOLD)
    if not scores:
        return {"threshold": base_threshold, "reason": "no_scores", "gap": 0.0, "spread": 0.0}

    ordered = sorted((float(score) for score in scores), reverse=True)
    top1 = ordered[0]
    top2 = ordered[1] if len(ordered) > 1 else top1
    gap = top1 - top2
    top_window = ordered[: min(5, len(ordered))]
    spread = max(top_window) - min(top_window) if len(top_window) > 1 else 0.0

    threshold = base_threshold
    reason = "baseline"
    if len(ordered) > 1 and gap >= 0.25:
        threshold = base_threshold - 0.08
        reason = "large_top_gap"
    elif len(ordered) > 2 and (gap <= 0.05 or spread <= 0.08):
        threshold = base_threshold + 0.08
        reason = "clustered_scores"

    return {
        "threshold": max(0.05, min(0.95, threshold)),
        "reason": reason,
        "gap": round(float(gap), 6),
        "spread": round(float(spread), 6),
    }


def _write_retrieval_audit(
    query: str,
    top_scores: list[float],
    number_of_chunks: int,
    unique_doc_ids: list[str],
    hallucination_guard_triggered: bool,
    threshold_decision: dict[str, Any],
) -> None:
    event = {
        "ts": time.time(),
        "query_hash": hashlib.sha256(str(query or "").encode("utf-8")).hexdigest(),
        "top_scores": [round(float(score), 6) for score in top_scores],
        "number_of_chunks": int(number_of_chunks),
        "unique_doc_ids": sorted({doc_id for doc_id in unique_doc_ids if doc_id}),
        "hallucination_guard_triggered": bool(hallucination_guard_triggered),
        "threshold_decision": threshold_decision,
    }
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _audit_lock:
            with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("[RAG] Retrieval audit write failed: %s", exc)


def _build_bm25_corpus(
    documents: list[Any],
    metadatas: list[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    bm25_corpus: list[str] = []
    bm25_meta: list[dict[str, Any]] = []
    for idx, raw_doc in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        for window_idx, window in enumerate(_chunk_text_util(str(raw_doc or ""), chunk_size=RAG_RERANK_WINDOW, overlap=RAG_CHUNK_OVERLAP)):
            cleaned_window = _normalize_chunk_text(window)
            if len(cleaned_window.split()) < 12:
                continue
            bm25_corpus.append(cleaned_window)
            bm25_meta.append({"meta": metadata, "chunk_idx": window_idx})
    return bm25_corpus, bm25_meta


def warmup_bm25_index() -> None:
    global _bm25_cache
    with _bm25_lock:
        collection = get_collection()
        total_chunks = int(collection.count())
        if total_chunks <= 0:
            _bm25_cache = None
            return

        all_results = collection.get(include=["documents", "metadatas"])
        all_docs = all_results.get("documents") or []
        all_metas = all_results.get("metadatas") or []

        bm25_corpus, bm25_meta = _build_bm25_corpus(all_docs, all_metas)
        if not bm25_corpus:
            _bm25_cache = None
            return

        tokenized_chunks = [chunk.split() for chunk in bm25_corpus]
        bm25 = BM25Okapi(tokenized_chunks)

        _bm25_cache = {
            "count": total_chunks,
            "bm25": bm25,
            "corpus": bm25_corpus,
            "meta": bm25_meta,
        }


def _get_bm25_cache(total_chunks: int) -> dict[str, Any] | None:
    with _bm25_lock:
        if not _bm25_cache:
            return None
        if int(_bm25_cache.get("count", 0)) != int(total_chunks):
            return None
        return _bm25_cache


def retrieve_chunks(
    query: str,
    top_k: int = 3,
    document_id: str | None = None,
) -> RetrievalResult:
    collection = get_collection()
    logger.info("[RAG] Query: %s", query)
    total_chunks = int(collection.count())
    logger.info("[RAG] Total chunks: %s", total_chunks)

    if total_chunks <= 0:
        _write_retrieval_audit(
            query=query,
            top_scores=[],
            number_of_chunks=0,
            unique_doc_ids=[],
            hallucination_guard_triggered=True,
            threshold_decision=_threshold_decision([]),
        )
        return {
            "chunks": [],
            "context": "No relevant context found in documents.",
            "guard_fired": True,
            "retrieval_score": None,
            "status": "no_context",
        }

    query_keywords = _extract_query_keywords(query)
    logger.info("[RAG] Keywords: %s", query_keywords)
    query_tokens = _keyword_query_tokens(query)
    embed_model = _get_embed_model()
    BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
    query_embedding = embed_model.encode(
        BGE_QUERY_PREFIX + query,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).tolist()

    vector_k = min(max(5, int(top_k)), total_chunks)
    where = {"doc_id": document_id} if document_id else None
    vector_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=vector_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = (vector_results.get("documents") or [[]])[0] if vector_results.get("documents") else []
    metadatas = (vector_results.get("metadatas") or [[]])[0] if vector_results.get("metadatas") else []
    distances = (vector_results.get("distances") or [[]])[0] if vector_results.get("distances") else []
    audit_scores = [max(0.0, 1.0 - (float(d) / 2.0)) for d in distances if isinstance(d, (int, float))]

    retrieved_count = len(docs)
    logger.info("[RAG] Retrieved (vector): %s", retrieved_count)

    candidates_by_sig: dict[str, dict[str, Any]] = {}

    def _register_candidate(
        text: str,
        metadata: dict[str, Any],
        vector_score: float = 0.0,
        bm25_score: float = 0.0,
        chunk_idx: int | None = None,
    ) -> None:
        clean_text = _normalize_chunk_text(_clean_broken_sentences(text))
        if not clean_text:
            return

        for phrase in TITLE_NOISE_PHRASES:
            clean_text = re.sub(re.escape(phrase), " ", clean_text, flags=re.IGNORECASE)
        clean_text = _normalize_chunk_text(clean_text)
        if len(clean_text.split()) < 12:
            return

        signature = re.sub(r"\s+", " ", clean_text.lower())
        if not signature:
            return

        page_val = metadata.get("page") if isinstance(metadata, dict) else None
        page = page_val if isinstance(page_val, int) else int(page_val) if isinstance(page_val, str) and page_val.isdigit() else None
        file_name = str((metadata or {}).get("file", "unknown.pdf"))
        doc_id = str((metadata or {}).get("doc_id", ""))

        existing = candidates_by_sig.get(signature)
        if existing:
            existing["vector_score"] = max(float(existing.get("vector_score", 0.0)), float(vector_score))
            existing["bm25_score"] = max(float(existing.get("bm25_score", 0.0)), float(bm25_score))
            return

        enriched_meta = dict(metadata or {})
        enriched_meta["source"] = file_name
        enriched_meta["chunk_id"] = (
            str(chunk_idx)
            if chunk_idx is not None
            else f"{doc_id or 'doc'}:{abs(hash(signature)) % 1000000}"
        )

        candidates_by_sig[signature] = {
            "text": clean_text,
            "file": file_name,
            "doc_id": doc_id,
            "page": page,
            "metadata": enriched_meta,
            "vector_score": float(vector_score),
            "bm25_score": float(bm25_score),
        }

    for idx, raw_chunk in enumerate(docs):
        metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        distance_val = distances[idx] if idx < len(distances) else None
        semantic_score = 0.0
        if isinstance(distance_val, (int, float)):
            semantic_score = max(0.0, 1.0 - (float(distance_val) / 2.0))

        vector_windows = _chunk_text_util(str(raw_chunk or ""), chunk_size=RAG_RERANK_WINDOW, overlap=RAG_CHUNK_OVERLAP)
        for window_idx, window in enumerate(vector_windows):
            _register_candidate(
                text=window,
                metadata=metadata,
                vector_score=semantic_score,
                bm25_score=0.0,
                chunk_idx=window_idx,
            )

    bm25_corpus: list[str] = []
    bm25_meta: list[dict[str, Any]] = []
    bm25: BM25Okapi | None = None

    cached = _get_bm25_cache(total_chunks) if document_id is None else None
    if cached:
        bm25 = cached.get("bm25")
        bm25_corpus = cached.get("corpus", [])
        bm25_meta = cached.get("meta", [])
    else:
        all_results = collection.get(where=where, include=["documents", "metadatas"])
        all_docs = all_results.get("documents") or []
        all_metas = all_results.get("metadatas") or []
        bm25_corpus, bm25_meta = _build_bm25_corpus(all_docs, all_metas)
        if bm25_corpus:
            tokenized_chunks = [chunk.split() for chunk in bm25_corpus]
            bm25 = BM25Okapi(tokenized_chunks)
            if document_id is None:
                with _bm25_lock:
                    global _bm25_cache
                    _bm25_cache = {
                        "count": total_chunks,
                        "bm25": bm25,
                        "corpus": bm25_corpus,
                        "meta": bm25_meta,
                    }

    if bm25 and bm25_corpus and query_tokens:
        bm25_scores = bm25.get_scores(query_tokens)
        top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:5]
        max_bm25 = max([bm25_scores[i] for i in top_bm25_indices], default=0.0)

        for bm25_idx in top_bm25_indices:
            raw_score = float(bm25_scores[bm25_idx])
            normalized_bm25 = (raw_score / max_bm25) if max_bm25 > 0 else 0.0
            _register_candidate(
                text=bm25_corpus[bm25_idx],
                metadata=bm25_meta[bm25_idx]["meta"],
                vector_score=0.0,
                bm25_score=normalized_bm25,
                chunk_idx=int(bm25_meta[bm25_idx]["chunk_idx"]),
            )

    combined_candidates = list(candidates_by_sig.values())
    if not combined_candidates:
        _write_retrieval_audit(
            query=query,
            top_scores=[],
            number_of_chunks=0,
            unique_doc_ids=[],
            hallucination_guard_triggered=True,
            threshold_decision=_threshold_decision([]),
        )
        return {
            "chunks": [],
            "context": "No relevant context found in documents.",
            "guard_fired": True,
            "retrieval_score": None,
            "status": "no_context",
        }

    candidates: list[dict[str, Any]] = []
    for candidate in combined_candidates:
        text = str(candidate.get("text", "")).strip()
        if not text:
            continue
        candidates.append(candidate)

    if not candidates:
        _write_retrieval_audit(
            query=query,
            top_scores=audit_scores,
            number_of_chunks=0,
            unique_doc_ids=[],
            hallucination_guard_triggered=True,
            threshold_decision=_threshold_decision([]),
        )
        return {
            "chunks": [],
            "context": "No relevant context found in documents.",
            "guard_fired": True,
            "retrieval_score": None,
            "status": "no_context",
        }
    # RRF hybrid scoring: combines vector and BM25 ranks without needing score normalization
    # Sort by each signal to get ranks, then fuse
    by_vector = sorted(candidates, key=lambda c: c.get("vector_score", 0.0), reverse=True)
    by_bm25 = sorted(candidates, key=lambda c: c.get("bm25_score", 0.0), reverse=True)
    vector_rank = {id(c): i for i, c in enumerate(by_vector)}
    bm25_rank = {id(c): i for i, c in enumerate(by_bm25)}
    RRF_K = RAG_RRF_K
    for candidate in candidates:
        cid = id(candidate)
        vr = vector_rank.get(cid, len(candidates))
        br = bm25_rank.get(cid, len(candidates))
        candidate["rrf_score"] = (1.0 / (RRF_K + vr)) + (1.0 / (RRF_K + br))
    candidates.sort(key=lambda c: c.get("rrf_score", 0.0), reverse=True)

    target_count = max(1, int(top_k))
    final_chunks = candidates[: min(target_count, len(candidates))]
    selected_chunks: list[RetrievedChunk] = []

    for candidate in final_chunks:
        text = _normalize_chunk_text(candidate.get("text", ""))
        if not text:
            continue
        selected_chunks.append(
            {
                "text": text,
                "file": str(candidate.get("file", "unknown.pdf")),
                "doc_id": str(candidate.get("doc_id", "")),
                "page": candidate.get("page") if isinstance(candidate.get("page"), int) else None,
                "metadata": dict(candidate.get("metadata", {})),
            }
        )

    context = "\n\n".join(
        chunk.get("text", "").strip()
        for chunk in selected_chunks
        if chunk.get("text", "").strip()
    )
    _write_retrieval_audit(
        query=query,
        top_scores=audit_scores,
        number_of_chunks=len(selected_chunks),
        unique_doc_ids=[chunk.get("doc_id", "") for chunk in selected_chunks],
        hallucination_guard_triggered=False,
        threshold_decision=_threshold_decision([]),
    )
    return {
        "chunks": selected_chunks,
        "context": context,
        "guard_fired": False,
        "retrieval_score": None,
        "status": "ok",
    }
