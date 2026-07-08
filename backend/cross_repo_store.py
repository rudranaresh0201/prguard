from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .core.logging import get_logger

logger = get_logger(__name__)

# Defaults to a local file for dev; on Render, CROSS_REPO_DB_PATH is set to a
# path on the persistent disk (see render.yaml) so announcements survive
# redeploys instead of living on the app's ephemeral filesystem.
_db_path_env = os.getenv("CROSS_REPO_DB_PATH", "").strip()
DB_PATH = Path(_db_path_env) if _db_path_env else Path(__file__).resolve().parent / "cross_repo.db"

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS breaking_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT NOT NULL,
                symbol TEXT NOT NULL,
                old_signature TEXT,
                new_signature TEXT,
                summary TEXT,
                severity TEXT,
                pr_url TEXT,
                announced_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_breaking_changes_symbol ON breaking_changes(symbol)"
        )
        conn.commit()
    logger.info("[CrossRepo] DB ready at %s", DB_PATH)


def announce_change(
    repo: str,
    symbol: str,
    old_signature: str,
    new_signature: str,
    summary: str,
    severity: str,
    pr_url: str,
) -> int:
    """Record a breaking change so other repos can discover it via check_symbols.

    Example::

        change_id = announce_change(
            repo="myorg/repo-a",
            symbol="charge",
            old_signature="charge(amount)",
            new_signature="charge(amount, currency)",
            summary="charge() now requires an explicit currency",
            severity="high",
            pr_url="https://github.com/myorg/repo-a/pull/42",
        )
    """
    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO breaking_changes
                (repo, symbol, old_signature, new_signature, summary, severity, pr_url, announced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo, symbol, old_signature, new_signature, summary, severity, pr_url, time.time()),
        )
        conn.commit()
        return int(cur.lastrowid)


def check_symbols(symbols: list[str], exclude_repo: str | None = None) -> list[dict[str, Any]]:
    """Return every announced breaking change matching any of the given symbols.

    Only the most recent announcement per symbol is returned. Announcements
    made by ``exclude_repo`` itself are skipped, so a repo checking after its
    own announcement doesn't just see its own change reflected back.

    Example::

        hits = check_symbols(["charge", "refund"], exclude_repo="myorg/repo-b")
    """
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    query = f"""
        SELECT * FROM breaking_changes
        WHERE symbol IN ({placeholders})
        ORDER BY announced_at DESC
    """
    with _lock, _connect() as conn:
        rows = conn.execute(query, symbols).fetchall()

    seen_symbols: set[str] = set()
    hits: list[dict[str, Any]] = []
    for row in rows:
        if exclude_repo and row["repo"] == exclude_repo:
            continue
        if row["symbol"] in seen_symbols:
            continue
        seen_symbols.add(row["symbol"])
        hits.append(dict(row))
    return hits
