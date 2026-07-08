"""Tests for the cross-repo breaking-change board: signing, storage, and
the FastAPI routes. Run with:

    pytest backend/tests/test_cross_repo.py -v
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the DB and signing key at throwaway files so tests never touch
    the real dev/prod database, and reload the modules so their module-level
    path constants pick up the patched env vars."""
    monkeypatch.setenv("CROSS_REPO_DB_PATH", str(tmp_path / "test_cross_repo.db"))
    monkeypatch.setenv("CROSS_REPO_SIGNING_KEY_PATH", str(tmp_path / "test_signing.key"))

    from backend import cross_repo_signing, cross_repo_store

    importlib.reload(cross_repo_signing)
    importlib.reload(cross_repo_store)
    cross_repo_store.init_db()
    return cross_repo_store, cross_repo_signing


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_sign_and_verify_round_trip(isolated_backend):
    _, signing = isolated_backend
    payload = {"repo": "a", "symbol": "b", "announced_at": 1.0}
    sig = signing.sign(payload)
    assert signing.verify(payload, sig) is True


def test_verify_fails_on_tampered_payload(isolated_backend):
    _, signing = isolated_backend
    payload = {"repo": "a", "symbol": "b", "announced_at": 1.0}
    sig = signing.sign(payload)
    tampered = {**payload, "symbol": "b-tampered"}
    assert signing.verify(tampered, sig) is False


def test_verify_fails_on_garbage_signature(isolated_backend):
    _, signing = isolated_backend
    payload = {"repo": "a", "symbol": "b", "announced_at": 1.0}
    assert signing.verify(payload, "not-a-real-signature") is False


def test_verify_with_key_matches_own_pubkey(isolated_backend):
    _, signing = isolated_backend
    payload = {"repo": "a", "symbol": "b", "announced_at": 1.0}
    sig = signing.sign(payload)
    pubkey = signing.get_public_key_b64()
    assert signing.verify_with_key(payload, sig, pubkey) is True


def test_verify_with_key_rejects_wrong_key(isolated_backend):
    _, signing = isolated_backend
    payload = {"repo": "a", "symbol": "b", "announced_at": 1.0}
    sig = signing.sign(payload)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64

    wrong_pub = base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    assert signing.verify_with_key(payload, sig, wrong_pub) is False


def test_signing_key_persists_across_reload(isolated_backend, tmp_path, monkeypatch):
    """The whole point of persisting the key is that old signatures stay
    verifiable after a restart -- prove the key doesn't change on reload."""
    _, signing = isolated_backend
    pubkey_before = signing.get_public_key_b64()

    importlib.reload(signing)
    pubkey_after = signing.get_public_key_b64()

    assert pubkey_before == pubkey_after


# ---------------------------------------------------------------------------
# Store: announce / check
# ---------------------------------------------------------------------------


def test_announce_returns_signed_record(isolated_backend):
    store, _ = isolated_backend
    record = store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    assert record["id"] >= 1
    assert record["sig"]
    assert record["repo"] == "org/a"


def test_check_finds_announced_symbol(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    hits = store.check_symbols(["charge"], exclude_repo="org/b")
    assert len(hits) == 1
    assert hits[0]["repo"] == "org/a"
    assert hits[0]["sig"]


def test_check_returns_empty_for_unannounced_symbol(isolated_backend):
    store, _ = isolated_backend
    assert store.check_symbols(["nonexistent"], exclude_repo="org/b") == []


def test_check_excludes_own_announcement(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    hits = store.check_symbols(["charge"], exclude_repo="org/a")
    assert hits == []


def test_check_scoped_to_expected_repo_matches(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    hits = store.check_symbols(
        ["charge"], exclude_repo="org/b", expected_repos={"charge": "org/a"}
    )
    assert len(hits) == 1


def test_check_scoped_to_wrong_repo_finds_nothing(isolated_backend):
    """The exact collision bug we found and fixed: two unrelated repos both
    define `charge`; scoping must reject the one you didn't ask for."""
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "real change", "high", "http://x")
    hits = store.check_symbols(
        ["charge"], exclude_repo="org/b", expected_repos={"charge": "org/unrelated"}
    )
    assert hits == []


def test_check_returns_most_recent_announcement_per_symbol(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "first", "low", "http://1")
    store.announce_change("org/a", "charge", "f(a,b)", "f(a,b,c)", "second", "high", "http://2")
    hits = store.check_symbols(["charge"], exclude_repo="org/b")
    assert len(hits) == 1
    assert hits[0]["summary"] == "second"


def test_verify_record_true_for_untampered_hit(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    hit = store.check_symbols(["charge"], exclude_repo="org/b")[0]
    assert store.verify_record(hit) is True


def test_verify_record_false_for_tampered_hit(isolated_backend):
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    hit = store.check_symbols(["charge"], exclude_repo="org/b")[0]
    hit["new_signature"] = "f(a,b,c) -- TAMPERED"
    assert store.verify_record(hit) is False


def test_verify_record_false_for_missing_sig(isolated_backend):
    store, _ = isolated_backend
    record = {
        "repo": "org/a",
        "symbol": "charge",
        "old_signature": "f(a)",
        "new_signature": "f(a,b)",
        "summary": "sum",
        "severity": "high",
        "pr_url": "http://x",
        "announced_at": 1.0,
        "sig": None,
    }
    assert store.verify_record(record) is False


def test_init_db_is_idempotent(isolated_backend):
    """Calling init_db() again (e.g. on every startup) must not blow away data."""
    store, _ = isolated_backend
    store.announce_change("org/a", "charge", "f(a)", "f(a,b)", "sum", "high", "http://x")
    store.init_db()
    hits = store.check_symbols(["charge"], exclude_repo="org/b")
    assert len(hits) == 1
