"""Capture the run environment so a result can be reproduced later.

Ported from the research pipeline's `reproducibility/env.py`. The tracked-library
list is retargeted: the original watched DIPY, nilearn and lifelines, none of
which this project imports. It now watches the stack that actually determines a
CogniSense number -- torch and librosa above all, since a torchaudio/librosa
version bump changes MFCC output and therefore changes every speech score.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

_TRACKED_LIBS = (
    "numpy", "scipy", "sklearn", "torch", "librosa", "soundfile",
    "fastapi", "pydantic", "sqlalchemy", "uvicorn",
)


@dataclass
class RunEnv:
    python_version: str
    platform: str
    git_commit: str | None
    git_dirty: bool
    cli_argv: list[str] = field(default_factory=list)
    lib_versions: dict[str, str] = field(default_factory=dict)
    gpu: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self, libs: tuple[str, ...] = ("torch", "librosa", "sklearn", "numpy")) -> str:
        """One-line version string for a report header."""
        return " / ".join(f"{k} {self.lib_versions.get(k, '?')}" for k in libs)


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _lib_version(name: str) -> str:
    try:
        mod = importlib.import_module(name)
        return getattr(mod, "__version__", "unknown")
    except Exception:
        # Deliberately broad: a library that raises on import should degrade
        # the header, not abort the run that was about to produce a result.
        return "not-installed"


def _detect_gpu() -> str | None:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def capture_env() -> RunEnv:
    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    return RunEnv(
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        git_commit=commit,
        git_dirty=dirty,
        cli_argv=list(sys.argv),
        lib_versions={name: _lib_version(name) for name in _TRACKED_LIBS},
        gpu=_detect_gpu(),
    )


def hash_config(config: dict[str, Any]) -> str:
    """Stable short hash of a config dict; used to key result files."""
    canonical = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(canonical).hexdigest()[:12]
