from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .core.logging import get_logger

logger = get_logger(__name__)

# Defaults to a local file for dev; on Render, CROSS_REPO_SIGNING_KEY_PATH is
# set to a path on the persistent disk (see render.yaml). The key MUST stay
# stable across redeploys -- a signature is only useful if the public key
# used to verify it later still matches the key that made it.
_key_path_env = os.getenv("CROSS_REPO_SIGNING_KEY_PATH", "").strip()
KEY_PATH = (
    Path(_key_path_env) if _key_path_env else Path(__file__).resolve().parent / "cross_repo_signing.key"
)

_lock = threading.Lock()
_private_key: Ed25519PrivateKey | None = None


def _load_or_create_key() -> Ed25519PrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key
    with _lock:
        if _private_key is not None:
            return _private_key
        if KEY_PATH.exists():
            raw = base64.b64decode(KEY_PATH.read_text().strip())
            _private_key = Ed25519PrivateKey.from_private_bytes(raw)
            logger.info("[CrossRepoSigning] Loaded existing signing key from %s", KEY_PATH)
        else:
            KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _private_key = Ed25519PrivateKey.generate()
            raw = _private_key.private_bytes(
                encoding=Encoding.Raw,
                format=PrivateFormat.Raw,
                encryption_algorithm=NoEncryption(),
            )
            KEY_PATH.write_text(base64.b64encode(raw).decode())
            logger.info("[CrossRepoSigning] Generated new signing key at %s", KEY_PATH)
        return _private_key


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(payload: dict[str, Any]) -> str:
    """Sign a canonical JSON payload with the service's Ed25519 key.

    Example::

        sig = sign({"repo": "myorg/repo-a", "symbol": "charge", "announced_at": 1.0})
    """
    key = _load_or_create_key()
    signature = key.sign(_canonical(payload))
    return base64.b64encode(signature).decode()


def get_public_key_b64() -> str:
    """Return this service's Ed25519 public key, base64-encoded.

    Example::

        pubkey = get_public_key_b64()
    """
    key = _load_or_create_key()
    raw = key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def verify(payload: dict[str, Any], signature_b64: str) -> bool:
    """Verify a signature against this service's own public key.

    Example::

        ok = verify({"repo": "myorg/repo-a", ...}, sig)
    """
    key = _load_or_create_key()
    public_key = key.public_key()
    try:
        public_key.verify(base64.b64decode(signature_b64), _canonical(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_with_key(payload: dict[str, Any], signature_b64: str, public_key_b64: str) -> bool:
    """Verify a signature against an arbitrary (e.g. previously fetched) public key.

    Lets a caller verify offline forever after fetching the pubkey once from
    ``/cross-repo/pubkey`` -- no need to trust this service at verify-time.

    Example::

        ok = verify_with_key(payload, sig, pubkey_fetched_earlier)
    """
    try:
        raw = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
        public_key.verify(base64.b64decode(signature_b64), _canonical(payload))
        return True
    except (InvalidSignature, ValueError):
        return False
