from __future__ import annotations

import hashlib
import traceback
import uuid
from pathlib import Path

from ..core.logging import get_logger
from ..db import get_collection
from ..ingestion import ingest_pdf_file_path
from ..retrieval import warmup_bm25_index
from ..storage import upload_pdf_to_r2, build_r2_key
from ..tasks import set_task_status, set_task_error

logger = get_logger(__name__)


def run_ingest_task(task_id: str, save_path: Path, safe_name: str, actual_size: int) -> None:
    doc_id = uuid.uuid4().hex
    s3_key = build_r2_key(doc_id, safe_name)

    logger.info(
        "[INGEST] Starting task_id=%s filename=%s size_bytes=%d",
        task_id, safe_name, actual_size,
    )

    try:
        set_task_status(task_id, "processing")

        # -------- HASH COMPUTE --------
        hasher = hashlib.sha256()
        with save_path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        content_hash = hasher.hexdigest()
        logger.info("[INGEST] SHA-256 hash computed: %s filename=%s", content_hash, safe_name)

        collection = get_collection()

        # -------- DEDUP CHECK --------
        existing = collection.get(where={"content_hash": content_hash})
        if existing.get("ids"):
            logger.info(
                "[INGEST] Duplicate detected (hash=%s), skipping filename=%s",
                content_hash, safe_name,
            )
            set_task_status(task_id, "done")
            return

        # -------- R2 UPLOAD (NON-FATAL) --------
        try:
            upload_pdf_to_r2(save_path, doc_id, safe_name)
            logger.info("[INGEST] R2 upload succeeded s3_key=%s", s3_key)
        except Exception as e:
            logger.warning("[INGEST] R2 upload failed (continuing): %s", e)

        # -------- INGEST INTO CHROMA FIRST --------
        logger.info("[INGEST] Calling ingest_pdf_file_path for filename=%s", safe_name)
        result = ingest_pdf_file_path(
            str(save_path),
            safe_name,
            actual_size,
            doc_id=doc_id,
            s3_key=s3_key,
            file_hash=content_hash,
        )

        # -------- DELETE STALE ONLY AFTER SUCCESSFUL INGEST --------
        # Safe to delete now — new chunks are confirmed stored under new doc_id
        collection.delete(where={
            "$and": [
                {"file": {"$eq": safe_name}},
                {"doc_id": {"$ne": doc_id}},
            ]
        })
        logger.info("[INGEST] Deleted stale chunks for filename=%s (kept new doc_id=%s)", safe_name, doc_id)

        # -------- BM25 REBUILD --------
        try:
            warmup_bm25_index()
            logger.info("[INGEST] BM25 index rebuilt")
        except Exception as e:
            logger.warning("[BM25] Warmup failed: %s", e)

        # -------- INGESTION QUALITY LOG --------
        # result["chunks"] is the integer count of stored chunks (not a list)
        chunk_count = result.get("chunks", 0) if isinstance(result, dict) else 0

        logger.info(
            "[INGEST] Complete event=ingestion_complete doc_id=%s filename=%s chunks=%d",
            doc_id, safe_name, chunk_count,
        )

        if 0 < chunk_count < 5:
            logger.warning(
                "[INGEST] Low chunk count (%d) — possible scanned/image-only PDF filename=%s",
                chunk_count, safe_name,
            )

        # -------- SUCCESS --------
        set_task_status(task_id, "done")
        logger.info("[INGEST] Task succeeded task_id=%s filename=%s doc_id=%s chunks=%d",
                    task_id, safe_name, doc_id, chunk_count)

    except Exception as e:
        logger.error(
            "[INGEST] Task FAILED task_id=%s filename=%s error=%s\n%s",
            task_id, safe_name, e, traceback.format_exc(),
        )

        try:
            get_collection().delete(where={"doc_id": doc_id})
            logger.info("[INGEST] Rolled back partial chunks for doc_id=%s", doc_id)
        except Exception as rollback_err:
            logger.warning("[INGEST] Rollback failed: %s", rollback_err)

        set_task_status(task_id, "failed")
        set_task_error(task_id, str(e))

    finally:
        try:
            save_path.unlink()
            logger.debug("[INGEST] Temp file deleted: %s", save_path)
        except OSError as e:
            logger.warning("[INGEST] Could not delete temp file %s: %s", save_path, e)