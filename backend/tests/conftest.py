"""Make `core` (repo root) and `app` (backend/) importable from the test run.

Mirrors what backend/app/__init__.py does for the server, so `pytest` works
regardless of which directory it is invoked from.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Must be set BEFORE any app module is imported: app.notifications.scheduler
# reads it at import time. Without this, TestClient(app) triggers the startup
# hook and a real push loop runs in the background, hitting the database
# underneath assertions and trying to reach live push services.
os.environ.setdefault("COGNISENSE_DISABLE_SCHEDULER", "1")

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent

for path in (str(_REPO_ROOT), str(_BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)
