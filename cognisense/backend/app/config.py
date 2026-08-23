"""Runtime configuration, read from the environment.

Nothing security-sensitive is hardcoded here: the JWT signing key must come from
the environment. In development a random key is generated per process (tokens
simply do not survive a restart); in production a missing key is fatal.
"""

import os
import secrets

ENV = os.getenv("COGNISENSE_ENV", "development").lower()
IS_PRODUCTION = ENV == "production"

ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("COGNISENSE_TOKEN_TTL_MINUTES", "60"))
JWT_ALGORITHM = "HS256"

# Maximum accepted size of an uploaded audio clip.
MAX_AUDIO_UPLOAD_BYTES = int(os.getenv("COGNISENSE_MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


def _load_secret_key() -> str:
    key = os.getenv("COGNISENSE_SECRET_KEY")
    if key:
        return key
    if IS_PRODUCTION:
        raise RuntimeError(
            "COGNISENSE_SECRET_KEY must be set when COGNISENSE_ENV=production"
        )
    return secrets.token_urlsafe(64)


SECRET_KEY = _load_secret_key()


def allowed_origins() -> list[str]:
    """CORS allow-list. Wildcards are never used, since the API is credentialed."""
    raw = os.getenv("COGNISENSE_ALLOWED_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if IS_PRODUCTION:
        return []
    return [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]
