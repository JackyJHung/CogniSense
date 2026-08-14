"""CogniSense backend package.

Puts the repository root on sys.path so that `core` -- the shared methodology
layer living alongside backend/ -- is importable when the server is started the
documented way, `uvicorn app.main:app` from inside backend/. That working
directory makes `app` importable but not its parent, so without this the
`from core...` imports would only resolve if the project were pip-installed,
and the README's run instructions do not install it.
"""
from __future__ import annotations

import sys
from pathlib import Path

# backend/app/__init__.py -> parents[0]=app, [1]=backend, [2]=repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
