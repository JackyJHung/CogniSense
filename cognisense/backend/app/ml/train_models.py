"""
Train demo PyTorch models on synthetic data.

This produces checkpoints so the FastAPI backend can run end-to-end without
needing a real clinical corpus. The synthetic distributions are crafted so
that:

  * "concerning" class has noisier MFCCs, slower simulated latencies, lower
    recall accuracy, lower lexical diversity.
  * "normal" class has the opposite.

REAL DEPLOYMENT MUST retrain on a labelled clinical dataset. The synthetic
models here are for smoke-testing the pipeline, not for clinical use.

Run:
    cd backend
    python -m app.ml.train_models
"""

from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from app.ml.speech_model import (
    SpeechBiomarkerCNN,
    MFCC_DIM,
    FRAMES,
    SPEECH_CKPT,
)
from app.ml.behavioral_model import (
    BehavioralBiomarkerMLP,
    BEHAV_FEATURES,
    BEHAV_CKPT,
)


SEED = 42


def set_seed(seed: int = SEED):
    np.random.seed(seed)
    torch.manual_seed(seed)


# -----------------------------------------------------------------------------
# Synthetic speech data
# -----------------------------------------------------------------------------

def make_speech_dataset(n_per_class: int = 800):
    """
    Synthesize MFCC-like tensors:
      - normal class: smooth sinusoidal bands + low noise
      - concerning class: more noise, disrupted bands (rough proxy for pause-heavy / disfluent speech)
    """
    rng = np.random.RandomState(SEED)
    X, y = [], []

    for cls in (0, 1):   # 0 = normal, 1 = concerning
        for _ in range(n_per_class):
            t = np.linspace(0, 4 * np.pi, FRAMES)
            bands = np.array([
                np.sin(t * (k + 1) * 0.5 + rng.uniform(0, np.pi))
                for k in range(MFCC_DIM)
            ])
            if cls == 0:
                noise = rng.normal(0, 0.3, size=bands.shape)
                mfcc = bands + noise
            else:
                # Disfluency proxy: random dropouts + heavier noise
                noise = rng.normal(0, 0.9, size=bands.shape)
                dropout_mask = (rng.rand(*bands.shape) > 0.15).astype(np.float32)
                mfcc = (bands * dropout_mask) + noise
            mfcc = (mfcc - mfcc.mean()) / (mfcc.std() + 1e-8)
            X.append(mfcc.astype(np.float32))
            y.append(cls)

    X = np.stack(X)
    y = np.array(y, dtype=np.float32)
    idx = rng.permutation(len(X))
    return X[idx], y[idx]


def train_speech_model(epochs: int = 6, batch_size: int = 32):
    set_seed()
    X, y = make_speech_dataset()
    ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True)

    model = SpeechBiomarkerCNN()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    for epoch in range(epochs):
        total, correct, losses = 0, 0, []
        for xb, yb in dl:
            opt.zero_grad()
            logits = model(xb).squeeze(-1)
            loss = loss_fn(logits, yb)
            loss.backward()
            opt.step()
            losses.append(loss.item())
            preds = (torch.sigmoid(logits) > 0.5).float()
            correct += (preds == yb).sum().item()
            total += len(yb)
        print(f"[speech] epoch {epoch+1}: loss={np.mean(losses):.4f} acc={correct/total:.3f}")

    torch.save(model.state_dict(), SPEECH_CKPT)
    print(f"[speech] saved checkpoint -> {SPEECH_CKPT}")


# -----------------------------------------------------------------------------
# Synthetic behavioral data
# -----------------------------------------------------------------------------

def make_behavioral_dataset(n_per_class: int = 1500):
    """
    Synthesize feature vectors. Normal class: high accuracy, normal latency,
    high lexical diversity. Concerning class: low accuracy, slower latency,
    low diversity.
    """
    rng = np.random.RandomState(SEED)
    X, y = [], []

    for cls in (0, 1):
        for _ in range(n_per_class):
            if cls == 0:
                # normal
                activity_rec = np.clip(rng.normal(0.78, 0.12), 0, 1)
                assoc = np.clip(rng.normal(0.82, 0.12), 0, 1)
                lat_z = rng.normal(0.0, 0.4)
                lex_div = np.clip(rng.normal(0.6, 0.12), 0, 1)
                word_count_norm = np.clip(rng.normal(1.0, 0.2), 0, 2)
                lat_var = abs(rng.normal(0.1, 0.06))
                checkin_cons = np.clip(rng.normal(0.9, 0.1), 0, 1)
                speech = np.clip(rng.normal(0.8, 0.1), 0, 1)
            else:
                # concerning
                activity_rec = np.clip(rng.normal(0.45, 0.15), 0, 1)
                assoc = np.clip(rng.normal(0.45, 0.17), 0, 1)
                lat_z = rng.normal(1.5, 0.6)
                lex_div = np.clip(rng.normal(0.35, 0.12), 0, 1)
                word_count_norm = np.clip(rng.normal(0.5, 0.2), 0, 2)
                lat_var = abs(rng.normal(0.35, 0.1))
                checkin_cons = np.clip(rng.normal(0.7, 0.15), 0, 1)
                speech = np.clip(rng.normal(0.4, 0.15), 0, 1)

            feats = np.array([
                activity_rec, assoc, lat_z, lex_div,
                word_count_norm, lat_var, checkin_cons, speech,
            ], dtype=np.float32)
            X.append(feats)
            y.append(cls)

    X = np.stack(X)
    y = np.array(y, dtype=np.float32)
    idx = rng.permutation(len(X))
    return X[idx], y[idx]


def train_behavioral_model(epochs: int = 30, batch_size: int = 64):
    set_seed()
    X, y = make_behavioral_dataset()
    ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True)

    model = BehavioralBiomarkerMLP()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    for epoch in range(epochs):
        total, correct, losses = 0, 0, []
        for xb, yb in dl:
            opt.zero_grad()
            logits = model(xb).squeeze(-1)
            loss = loss_fn(logits, yb)
            loss.backward()
            opt.step()
            losses.append(loss.item())
            preds = (torch.sigmoid(logits) > 0.5).float()
            correct += (preds == yb).sum().item()
            total += len(yb)
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"[behav]  epoch {epoch+1}: loss={np.mean(losses):.4f} acc={correct/total:.3f}")

    torch.save(model.state_dict(), BEHAV_CKPT)
    print(f"[behav]  saved checkpoint -> {BEHAV_CKPT}")


def main():
    print("=" * 50)
    print("Training speech biomarker CNN on synthetic data")
    print("=" * 50)
    train_speech_model()

    print()
    print("=" * 50)
    print("Training behavioral biomarker MLP on synthetic data")
    print("=" * 50)
    train_behavioral_model()

    print()
    print("Done. These are DEMO models. Retrain on labelled clinical data for real use.")


if __name__ == "__main__":
    main()
