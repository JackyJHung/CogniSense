"""Make `core` (repo root) and `app` (backend/) importable from the test run.

Mirrors what backend/app/__init__.py does for the server, so `pytest` works
regardless of which directory it is invoked from.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent

for path in (str(_REPO_ROOT), str(_BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)
