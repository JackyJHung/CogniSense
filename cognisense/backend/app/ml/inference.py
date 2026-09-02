"""Shared inference utilities for the PyTorch biomarker models."""

from __future__ import annotations
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


def normalize_array(arr: np.ndarray) -> np.ndarray:
    """Zero-mean, unit-variance normalisation."""
    return (arr - arr.mean()) / (arr.std() + 1e-8)


class NormalcyScorer:
    """Load a checkpoint (if present) and score inputs as 'normalcy' in [0,1].

    The wrapped model outputs P(concerning) logits; scores are flipped so
    HIGHER = more normal.
    """

    def __init__(self, model: nn.Module, ckpt_path: Path, device: str = "cpu"):
        self.device = torch.device(device)
        self.model = model.to(self.device)
        if ckpt_path.exists():
            state = torch.load(ckpt_path, map_location=self.device)
            self.model.load_state_dict(state)
        self.model.eval()

    @torch.no_grad()
    def score_array(self, arr: np.ndarray) -> float:
        x = torch.from_numpy(arr).unsqueeze(0).to(self.device)
        logits = self.model(x)
        p_concern = torch.sigmoid(logits).item()
        return float(1.0 - p_concern)
