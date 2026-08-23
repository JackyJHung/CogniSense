"""
Behavioral-biomarker PyTorch model.

Takes a feature vector capturing the user's daily performance and returns a
normalcy score in [0,1] (higher = more normal).

Features (all z-scored vs. user's own rolling baseline or the synthetic training
distribution):

  0. activity_recall_accuracy           -- overlap of recalled vs. planned
  1. association_accuracy               -- 0..1 correct on image cue task
  2. avg_response_latency_ms_z          -- slower than baseline => concerning
  3. linguistic_richness                -- lexical diversity of recalled activities
  4. word_count_recalled                -- absolute count of words in recall
  5. latency_variance                   -- within-day variance of response latency
  6. checkin_consistency                -- fraction of 3 daily check-ins completed
  7. speech_biomarker_score             -- from the speech model, 0..1

The model is a small MLP; it trains quickly and runs on CPU which suits both
desktop and mobile deployments.
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
import torch.nn as nn

from app.ml.inference import CHECKPOINT_DIR, NormalcyScorer


BEHAV_FEATURES = 8
BEHAV_CKPT = CHECKPOINT_DIR / "behavioral_mlp.pt"


class BehavioralBiomarkerMLP(nn.Module):
    def __init__(self, in_features: int = BEHAV_FEATURES):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, 64),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x)


# -----------------------------------------------------------------------------
# Feature extraction helpers
# -----------------------------------------------------------------------------

def lexical_diversity(text: str) -> float:
    """Type/token ratio. A naive proxy for linguistic richness."""
    if not text.strip():
        return 0.0
    tokens = [t.lower() for t in text.split() if t.strip()]
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def activity_overlap(planned: str, recalled: str) -> float:
    """
    Fraction of planned-activity tokens that appear in recall.
    Very rough; a real implementation would use lemma matching or embedding similarity.
    """
    planned_tokens = {t.lower().strip(".,!?") for t in planned.split() if len(t) > 2}
    recalled_tokens = {t.lower().strip(".,!?") for t in recalled.split() if len(t) > 2}
    if not planned_tokens:
        return 0.0
    return len(planned_tokens & recalled_tokens) / len(planned_tokens)


def build_behavioral_feature_vector(
    activity_recall_accuracy: float,
    association_accuracy: float,
    avg_response_latency_ms: int,
    baseline_latency_ms: int,
    recalled_text: str,
    latency_variance: float,
    checkin_consistency: float,
    speech_biomarker_score: float,
) -> np.ndarray:
    # Z-score of latency vs. the user's own baseline. Large positive = slower.
    latency_z = (avg_response_latency_ms - baseline_latency_ms) / max(baseline_latency_ms, 1) \
        if baseline_latency_ms else 0.0
    # Clip to a reasonable range for the model
    latency_z = float(np.clip(latency_z, -2.0, 4.0))

    lex_div = lexical_diversity(recalled_text)
    word_count = float(len(recalled_text.split()))
    # Normalise word count to roughly 0..1 (30 words ~= typical day recap)
    word_count_norm = float(np.clip(word_count / 30.0, 0.0, 2.0))

    feats = np.array([
        float(activity_recall_accuracy),
        float(association_accuracy),
        latency_z,
        lex_div,
        word_count_norm,
        float(latency_variance),
        float(checkin_consistency),
        float(speech_biomarker_score),
    ], dtype=np.float32)
    return feats


# -----------------------------------------------------------------------------
# Inference wrapper
# -----------------------------------------------------------------------------

class BehavioralScorer(NormalcyScorer):
    def __init__(self, ckpt_path: Path = BEHAV_CKPT, device: str = "cpu"):
        super().__init__(BehavioralBiomarkerMLP(), ckpt_path, device)

    def score(self, features: np.ndarray) -> float:
        """
        features: shape (BEHAV_FEATURES,)
        returns: float in [0,1], 'normalcy' score (HIGHER = more normal).
        """
        return self.score_array(features)
