from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import cross_repo_signing
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
                announced_at REAL NOT NULL,
                sig TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_breaking_changes_symbol ON breaking_changes(symbol)"
        )
        # Migration: existing deployments created the table before `sig` existed.
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(breaking_changes)")}
        if "sig" not in existing_cols:
            conn.execute("ALTER TABLE breaking_changes ADD COLUMN sig TEXT")
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
) -> dict[str, Any]:
    """Record a breaking change so other repos can discover it via check_symbols.

    The record is signed with this service's Ed25519 key before it's stored,
    so any caller can later verify it actually came from this board and was
    not tampered with in transit or forged -- fetch the public key once from
    ``get_public_key_b64`` and verify offline forever after.

    Example::

        record = announce_change(
            repo="myorg/repo-a",
            symbol="charge",
            old_signature="charge(amount)",
            new_signature="charge(amount, currency)",
            summary="charge() now requires an explicit currency",
            severity="high",
            pr_url="https://github.com/myorg/repo-a/pull/42",
        )
        record["id"], record["sig"]
    """
    announced_at = time.time()
    signable = {
        "repo": repo,
        "symbol": symbol,
        "old_signature": old_signature,
        "new_signature": new_signature,
        "summary": summary,
        "severity": severity,
        "pr_url": pr_url,
        "announced_at": announced_at,
    }
    sig = cross_repo_signing.sign(signable)

    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO breaking_changes
                (repo, symbol, old_signature, new_signature, summary, severity, pr_url, announced_at, sig)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo, symbol, old_signature, new_signature, summary, severity, pr_url, announced_at, sig),
        )
        conn.commit()
        return {**signable, "id": int(cur.lastrowid), "sig": sig}


def check_symbols(
    symbols: list[str],
    exclude_repo: str | None = None,
    expected_repos: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return every announced breaking change matching any of the given symbols.

    Symbol names are global across the whole board, not namespaced per repo
    -- ``charge`` announced by one repo and an unrelated ``charge`` announced
    by a totally different repo are indistinguishable by name alone. When
    the caller actually knows which repo a symbol is supposed to come from
    (the common case -- an import statement tells you both), pass it in
    ``expected_repos`` to scope that symbol's match to only that repo and
    avoid false positives from an unrelated same-named symbol elsewhere.
    Symbols not present in ``expected_repos`` fall back to matching any repo.

    Only the most recent (repo-matching, if scoped) announcement per symbol
    is returned. Announcements made by ``exclude_repo`` itself are always
    skipped, so a repo checking after its own announcement doesn't just see
    its own change reflected back.

    Example::

        hits = check_symbols(
            ["charge", "refund"],
            exclude_repo="myorg/repo-b",
            expected_repos={"charge": "myorg/repo-a"},
        )
    """
    if not symbols:
        return []
    expected_repos = expected_repos or {}
    placeholders = ",".join("?" for _ in symbols)
    query = f"""
        SELECT * FROM breaking_changes
        WHERE symbol IN ({placeholders})
        ORDER BY announced_at DESC, id DESC
    """
    with _lock, _connect() as conn:
        rows = conn.execute(query, symbols).fetchall()

    seen_symbols: set[str] = set()
    hits: list[dict[str, Any]] = []
    for row in rows:
        if exclude_repo and row["repo"] == exclude_repo:
            continue
        expected = expected_repos.get(row["symbol"])
        if expected and row["repo"] != expected:
            continue
        if row["symbol"] in seen_symbols:
            continue
        seen_symbols.add(row["symbol"])
        hits.append(dict(row))
    return hits


def verify_record(record: dict[str, Any]) -> bool:
    """Verify a change record's signature against this service's current key.

    ``record`` must contain the same fields ``announce_change`` signed
    (``repo``, ``symbol``, ``old_signature``, ``new_signature``, ``summary``,
    ``severity``, ``pr_url``, ``announced_at``) plus ``sig``.

    Example::

        ok = verify_record(hit)  # hit came from check_symbols()
    """
    if not record.get("sig"):
        return False
    signable = {
        "repo": record["repo"],
        "symbol": record["symbol"],
        "old_signature": record["old_signature"],
        "new_signature": record["new_signature"],
        "summary": record["summary"],
        "severity": record["severity"],
        "pr_url": record["pr_url"],
        "announced_at": record["announced_at"],
    }
    return cross_repo_signing.verify(signable, record["sig"])
