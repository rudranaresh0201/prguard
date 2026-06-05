from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

_is_rebuilding: bool = False
_rebuild_lock = threading.Lock()
_logger = logging.getLogger(__name__)


def is_rebuilding() -> bool:
    return _is_rebuilding


def is_rebuild_locked() -> bool:
    return _rebuild_lock.locked()


def rebuild_from_r2_if_empty() -> None:
    global _is_rebuilding

    # Lazy imports avoid circular dependencies at module load time.
    from ..db import get_collection
    from ..storage import list_all_pdfs_in_r2, download_pdf_from_r2
    from ..ingestion import ingest_pdf_file_path

    try:
        collection = get_collection()
        if collection.count() > 0:
            _logger.info("[REBUILD] DB already has documents — skipping rebuild.")
            return
    except Exception as exc:
        _logger.warning("[REBUILD] Could not check DB, skipping: %s", exc)
        return

    acquired = _rebuild_lock.acquire(blocking=False)
    if not acquired:
        _logger.info("[REBUILD] Rebuild already in progress.")
        return

    _is_rebuilding = True
    try:
        keys = list_all_pdfs_in_r2()
        _logger.info("[REBUILD] Found %d PDFs in R2.", len(keys))

        with tempfile.TemporaryDirectory() as tmpdir:
            for key in keys:
                filename = Path(key).name
                local_path = Path(tmpdir) / filename
                try:
                    download_pdf_from_r2(key, local_path)
                    ingest_pdf_file_path(
                        str(local_path),
                        filename,
                        local_path.stat().st_size,
                        s3_key=key,
                    )
                    _logger.info("[REBUILD] Ingested: %s", filename)
                except Exception as exc:
                    _logger.warning("[REBUILD] Skipping %s: %s", key, exc)
    except RuntimeError as exc:
        _logger.info("[REBUILD] R2 not configured, skipping: %s", exc)
    except Exception as exc:
        _logger.exception("[REBUILD] Unexpected error: %s", exc)
    finally:
        _is_rebuilding = False
        _rebuild_lock.release()
