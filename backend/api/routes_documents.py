from __future__ import annotations

import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import get_max_upload_bytes
from ..db import delete_document, get_all_records, get_s3_key_for_document
from ..storage import delete_pdf_from_r2
from ..services.ingestion_service import run_ingest_task
from ..tasks import create_task, get_task_status

router = APIRouter()


@router.get("/documents")
def list_documents():
    data = get_all_records()
    metadatas = data.get("metadatas") or []
    seen: set[str] = set()
    documents = []
    for meta in metadatas:
        if not isinstance(meta, dict):
            continue
        doc_id = str(meta.get("doc_id", "")).strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        documents.append({
            "doc_id": doc_id,
            "filename": meta.get("file", "unknown.pdf"),
            "size": meta.get("size", 0),
            "uploaded_at": meta.get("uploaded_at", ""),
            "s3_key": meta.get("s3_key", ""),
        })
    return {"documents": documents}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    max_bytes = get_max_upload_bytes()
    if len(pdf_bytes) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File exceeds the {max_mb} MB limit.")

    safe_name = Path(file.filename).name
    task_id = str(uuid.uuid4())

    # Write to a temp file; ingestion_service.run_ingest_task deletes it on completion.
    tmp_dir = Path(tempfile.mkdtemp())
    save_path = tmp_dir / safe_name
    save_path.write_bytes(pdf_bytes)

    create_task(task_id, save_path=save_path, safe_name=safe_name, actual_size=len(pdf_bytes))

    threading.Thread(
        target=run_ingest_task,
        args=(task_id, save_path, safe_name, len(pdf_bytes)),
        daemon=True,
    ).start()

    return {"task_id": task_id, "status": "pending"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.delete("/documents/{doc_id}")
def delete_doc(doc_id: str):
    # Retrieve s3_key BEFORE deleting chunks (metadata goes with chunks)
    s3_key = get_s3_key_for_document(doc_id)

    # Delete chunks from ChromaDB
    delete_document(doc_id)

    # Delete raw PDF from R2 (non-fatal if missing or R2 not configured)
    if s3_key:
        try:
            delete_pdf_from_r2(s3_key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "[DELETE] R2 delete failed for s3_key=%s doc_id=%s: %s", s3_key, doc_id, e
            )

    return {"message": f"Document {doc_id} deleted."}
