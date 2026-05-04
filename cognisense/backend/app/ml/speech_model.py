"""
Speech-biomarker PyTorch model.

Rationale: research on AD speech markers (e.g. Luz et al. ADReSS Challenge;
de la Fuente Garcia et al., 2020) shows that temporal + spectral features of
spontaneous speech (pauses, hesitation ratio, MFCC dynamics) differ between
cognitively normal older adults and those with MCI / early AD.

Architecture
------------
1-D convolutional encoder over MFCC frames, followed by a small classifier
head predicting P(cognitively-concerning speech pattern).

Input:  (batch, n_mfcc=40, n_frames=200)  -- computed via librosa.feature.mfcc
        on ~5-second 16 kHz mono audio.
Output: (batch, 1) probability of "concerning" pattern.

Training note: This repository ships with a *synthetic-data* trained checkpoint
for demo / end-to-end runs. Real deployment requires fine-tuning on a labelled
clinical corpus (DementiaBank Pitt, ADReSS, etc.) with appropriate ethics
approval.
"""

from __future__ import annotations
from pathlib import Path

import torch
import torch.nn as nn
import numpy as np

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


MFCC_DIM = 40
FRAMES = 200
MODEL_DIR = Path(__file__).resolve().parent / "checkpoints"
MODEL_DIR.mkdir(exist_ok=True)
SPEECH_CKPT = MODEL_DIR / "speech_cnn.pt"


class SpeechBiomarkerCNN(nn.Module):
    def __init__(self, n_mfcc: int = MFCC_DIM, n_frames: int = FRAMES):
        super().__init__()
        # Treat MFCC dim as channels, frames as sequence
        self.features = nn.Sequential(
            nn.Conv1d(n_mfcc, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(64, 128, kernel_size=5, padding=2),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(128, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, n_mfcc, n_frames)
        h = self.features(x)
        logits = self.classifier(h)
        return logits  # raw logits; apply sigmoid outside


# -----------------------------------------------------------------------------
# Preprocessing: audio file -> MFCC tensor
# -----------------------------------------------------------------------------

def audio_to_mfcc(audio_path: str | Path, sr: int = 16000, duration_s: float = 5.0) -> np.ndarray:
    """
    Load an audio file and return a (MFCC_DIM, FRAMES) numpy array, padded or
    trimmed to exactly FRAMES frames.
    """
    if not LIBROSA_AVAILABLE:
        raise RuntimeError("librosa is required for audio preprocessing")

    y, _ = librosa.load(audio_path, sr=sr, duration=duration_s, mono=True)
    # Pad short clips
    target_len = int(sr * duration_s)
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=MFCC_DIM)
    # Fix frames
    if mfcc.shape[1] >= FRAMES:
        mfcc = mfcc[:, :FRAMES]
    else:
        pad = FRAMES - mfcc.shape[1]
        mfcc = np.pad(mfcc, ((0, 0), (0, pad)))
    # Normalise
    mfcc = (mfcc - mfcc.mean()) / (mfcc.std() + 1e-8)
    return mfcc.astype(np.float32)


# -----------------------------------------------------------------------------
# Inference wrapper
# -----------------------------------------------------------------------------

class SpeechScorer:
    """Thin wrapper: load checkpoint and score an audio file -> 0..1."""

    def __init__(self, ckpt_path: Path = SPEECH_CKPT, device: str = "cpu"):
        self.device = torch.device(device)
        self.model = SpeechBiomarkerCNN().to(self.device)
        if ckpt_path.exists():
            state = torch.load(ckpt_path, map_location=self.device)
            self.model.load_state_dict(state)
        self.model.eval()

    @torch.no_grad()
    def score_audio(self, audio_path: str | Path) -> float:
        """
        Returns a 'normalcy' score in [0,1] where HIGHER = more normal speech
        pattern. (The model outputs P(concerning); we return 1 - P.)
        """
        mfcc = audio_to_mfcc(audio_path)
        x = torch.from_numpy(mfcc).unsqueeze(0).to(self.device)   # (1, n_mfcc, frames)
        logits = self.model(x)
        p_concern = torch.sigmoid(logits).item()
        return float(1.0 - p_concern)

    @torch.no_grad()
    def score_mfcc_array(self, mfcc: np.ndarray) -> float:
        """Score from a pre-computed MFCC array (for testing without audio)."""
        x = torch.from_numpy(mfcc).unsqueeze(0).to(self.device)
        logits = self.model(x)
        p_concern = torch.sigmoid(logits).item()
        return float(1.0 - p_concern)
