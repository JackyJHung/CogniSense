"""Unit tests for app/ml/train_models.py.

The real training entry points use large synthetic datasets and many epochs; the
tests below monkeypatch the dataset builders and checkpoint paths so the
training loops run in seconds while still exercising the real code paths.
"""

import numpy as np
import pytest
import torch

from app.ml import train_models
from app.ml.behavioral_model import BEHAV_FEATURES, BehavioralBiomarkerMLP
from app.ml.speech_model import FRAMES, MFCC_DIM, SpeechBiomarkerCNN
from app.ml.train_models import (
    SEED,
    main,
    make_behavioral_dataset,
    make_speech_dataset,
    set_seed,
    train_behavioral_model,
    train_speech_model,
)


# ---------- seeding ----------

def test_set_seed_makes_numpy_and_torch_deterministic():
    set_seed(123)
    a = (np.random.rand(3), torch.rand(3))
    set_seed(123)
    b = (np.random.rand(3), torch.rand(3))
    assert np.allclose(a[0], b[0])
    assert torch.allclose(a[1], b[1])
    set_seed(SEED)


# ---------- synthetic speech data ----------

def test_speech_dataset_shape_and_balance():
    X, y = make_speech_dataset(n_per_class=4)
    assert X.shape == (8, MFCC_DIM, FRAMES)
    assert X.dtype == np.float32
    assert y.shape == (8,)
    assert set(np.unique(y)) == {0.0, 1.0}
    assert y.sum() == 4


def test_speech_dataset_samples_are_normalised():
    X, _ = make_speech_dataset(n_per_class=3)
    for sample in X:
        assert sample.mean() == pytest.approx(0.0, abs=1e-4)
        assert sample.std() == pytest.approx(1.0, abs=1e-3)


def test_speech_dataset_is_shuffled_but_reproducible():
    X1, y1 = make_speech_dataset(n_per_class=8)
    X2, y2 = make_speech_dataset(n_per_class=8)
    assert np.array_equal(y1, y2)
    assert np.array_equal(X1, X2)
    # Shuffling means the labels are not left in blocked 0...0,1...1 order
    assert not np.array_equal(y1, np.sort(y1))


def test_concerning_speech_class_is_noisier_than_normal():
    X, y = make_speech_dataset(n_per_class=40)
    # Dropouts + heavier noise make the concerning class less smooth frame-to-frame
    roughness = np.abs(np.diff(X, axis=2)).mean(axis=(1, 2))
    assert roughness[y == 1].mean() > roughness[y == 0].mean()


# ---------- synthetic behavioral data ----------

def test_behavioral_dataset_shape_and_balance():
    X, y = make_behavioral_dataset(n_per_class=5)
    assert X.shape == (10, BEHAV_FEATURES)
    assert X.dtype == np.float32
    assert y.sum() == 5


def test_behavioral_dataset_features_stay_in_expected_ranges():
    X, _ = make_behavioral_dataset(n_per_class=50)
    activity, assoc, _, lex_div, word_count, lat_var, consistency, speech = X.T
    for col in (activity, assoc, lex_div, consistency, speech):
        assert col.min() >= 0.0 and col.max() <= 1.0
    assert word_count.min() >= 0.0 and word_count.max() <= 2.0
    assert lat_var.min() >= 0.0


def test_concerning_behavioral_class_is_slower_and_less_accurate():
    X, y = make_behavioral_dataset(n_per_class=100)
    normal, concerning = X[y == 0], X[y == 1]
    assert concerning[:, 0].mean() < normal[:, 0].mean()   # activity recall
    assert concerning[:, 1].mean() < normal[:, 1].mean()   # association accuracy
    assert concerning[:, 2].mean() > normal[:, 2].mean()   # latency z-score
    assert concerning[:, 3].mean() < normal[:, 3].mean()   # lexical diversity
    assert concerning[:, 7].mean() < normal[:, 7].mean()   # speech score


def test_behavioral_dataset_is_reproducible():
    X1, y1 = make_behavioral_dataset(n_per_class=10)
    X2, y2 = make_behavioral_dataset(n_per_class=10)
    assert np.array_equal(X1, X2) and np.array_equal(y1, y2)


# ---------- training loops ----------

@pytest.fixture
def tiny_speech_training(monkeypatch, tmp_path):
    ckpt = tmp_path / "speech_cnn.pt"
    monkeypatch.setattr(train_models, "SPEECH_CKPT", ckpt)
    monkeypatch.setattr(
        train_models, "make_speech_dataset", lambda *a, **kw: make_speech_dataset(n_per_class=4)
    )
    return ckpt


@pytest.fixture
def tiny_behavioral_training(monkeypatch, tmp_path):
    ckpt = tmp_path / "behavioral_mlp.pt"
    monkeypatch.setattr(train_models, "BEHAV_CKPT", ckpt)
    monkeypatch.setattr(
        train_models,
        "make_behavioral_dataset",
        lambda *a, **kw: make_behavioral_dataset(n_per_class=16),
    )
    return ckpt


def test_train_speech_model_writes_a_loadable_checkpoint(tiny_speech_training):
    train_speech_model(epochs=1, batch_size=4)

    assert tiny_speech_training.exists()
    state = torch.load(tiny_speech_training, map_location="cpu")
    SpeechBiomarkerCNN().load_state_dict(state)


def test_train_behavioral_model_writes_a_loadable_checkpoint(tiny_behavioral_training):
    train_behavioral_model(epochs=1, batch_size=8)

    assert tiny_behavioral_training.exists()
    state = torch.load(tiny_behavioral_training, map_location="cpu")
    BehavioralBiomarkerMLP().load_state_dict(state)


def test_train_behavioral_model_reduces_loss_over_epochs(tiny_behavioral_training, capsys):
    train_behavioral_model(epochs=10, batch_size=8)

    losses = [
        float(line.split("loss=")[1].split()[0])
        for line in capsys.readouterr().out.splitlines()
        if "loss=" in line
    ]
    assert len(losses) >= 2
    assert losses[-1] < losses[0]


def test_main_trains_both_models(monkeypatch, tiny_speech_training, tiny_behavioral_training):
    monkeypatch.setattr(train_models, "train_speech_model", lambda: train_speech_model(epochs=1, batch_size=4))
    monkeypatch.setattr(
        train_models, "train_behavioral_model", lambda: train_behavioral_model(epochs=1, batch_size=8)
    )

    main()

    assert tiny_speech_training.exists()
    assert tiny_behavioral_training.exists()
