from __future__ import annotations

import os


def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_max_upload_bytes() -> int:
    try:
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    except ValueError:
        max_mb = 50
    return max(1, max_mb) * 1024 * 1024
