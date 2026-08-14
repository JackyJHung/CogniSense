"""VAPID keypair management.

Web Push requires the server to sign each request with a P-256 key so the push
service (Google FCM, Mozilla autopush, ...) can tell that pushes to a given
subscription all come from the same application. The browser is handed the
matching PUBLIC key when it subscribes, and it will refuse pushes signed by any
other key.

That has one consequence worth stating plainly: **the keypair must be stable.**
Regenerate it and every existing subscription silently stops working, because
the browser checks the `applicationServerKey` it was subscribed with. So the
key is generated once, written to disk, and reused -- never generated per
process.

It lives in `backend/app/db/`, which .gitignore already excludes. It is a
private key: it must not be committed, and it should not be shared between a
development machine and a real deployment.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)

KEY_DIR = Path(__file__).resolve().parents[1] / "db"
PRIVATE_KEY_PATH = KEY_DIR / "vapid_private.pem"

# The `sub` claim in the VAPID JWT. Push services want a way to contact whoever
# is responsible for a misbehaving application server. Override in deployment.
VAPID_SUBJECT = os.environ.get("COGNISENSE_VAPID_SUBJECT", "mailto:admin@cognisense.local")


def _b64url(raw: bytes) -> str:
    """base64url, unpadded -- the encoding the Push API expects."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _load_private_key() -> ec.EllipticCurvePrivateKey | None:
    if not PRIVATE_KEY_PATH.exists():
        return None
    try:
        key = serialization.load_pem_private_key(
            PRIVATE_KEY_PATH.read_bytes(), password=None,
        )
    except Exception:
        logger.exception("VAPID key at %s is unreadable", PRIVATE_KEY_PATH)
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        logger.error("VAPID key at %s is not an EC key", PRIVATE_KEY_PATH)
        return None
    return key


def _generate_private_key() -> ec.EllipticCurvePrivateKey:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    PRIVATE_KEY_PATH.write_bytes(pem)
    try:
        # Best effort on Windows; owner-only on POSIX.
        os.chmod(PRIVATE_KEY_PATH, 0o600)
    except OSError:
        pass
    logger.info("generated a new VAPID keypair at %s", PRIVATE_KEY_PATH)
    return key


def ensure_keypair() -> ec.EllipticCurvePrivateKey:
    """Load the keypair, generating it on first run. Idempotent."""
    return _load_private_key() or _generate_private_key()


def public_key_b64() -> str:
    """The `applicationServerKey` the browser subscribes with.

    Base64url of the uncompressed P-256 point (65 bytes, leading 0x04), which is
    exactly what `PushManager.subscribe` wants.
    """
    key = ensure_keypair()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(raw)


def private_key_path() -> str:
    """Path handed to pywebpush as `vapid_private_key`."""
    ensure_keypair()
    return str(PRIVATE_KEY_PATH)
