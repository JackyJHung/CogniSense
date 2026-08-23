"""Unit tests for app/ml/speech_model.py."""

import numpy as np
import pytest
import soundfile as sf
import torch

from app.ml import speech_model
from app.ml.speech_model import (
    FRAMES,
    MFCC_DIM,
    SpeechBiomarkerCNN,
    SpeechScorer,
    audio_to_mfcc,
)


@pytest.fixture
def wav_file(tmp_path):
    """Write a short 16 kHz mono tone; returns a factory taking a duration."""

    def _write(duration_s: float = 5.0, name: str = "sample.wav", sr: int = 16000):
        t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
        y = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        path = tmp_path / name
        sf.write(path, y, sr)
        return path

    return _write


# ---------- model ----------

def test_cnn_forward_shape():
    model = SpeechBiomarkerCNN()
    out = model(torch.zeros(3, MFCC_DIM, FRAMES))
    assert out.shape == (3, 1)


def test_cnn_output_is_raw_logits_not_probabilities():
    model = SpeechBiomarkerCNN().eval()
    with torch.no_grad():
        out = model(torch.randn(8, MFCC_DIM, FRAMES) * 50)
    # Sigmoid would bound the output to (0, 1); logits are unbounded
    assert out.min().item() < 0.0 or out.max().item() > 1.0


def test_cnn_handles_custom_frame_count():
    model = SpeechBiomarkerCNN().eval()
    with torch.no_grad():
        # AdaptiveAvgPool1d makes the head independent of sequence length
        assert model(torch.zeros(1, MFCC_DIM, 64)).shape == (1, 1)


# ---------- audio_to_mfcc ----------

def test_audio_to_mfcc_shape_and_dtype(wav_file):
    mfcc = audio_to_mfcc(wav_file(5.0))
    assert mfcc.shape == (MFCC_DIM, FRAMES)
    assert mfcc.dtype == np.float32


def test_audio_to_mfcc_is_zero_mean_unit_variance(wav_file):
    mfcc = audio_to_mfcc(wav_file(5.0))
    assert mfcc.mean() == pytest.approx(0.0, abs=1e-4)
    assert mfcc.std() == pytest.approx(1.0, abs=1e-3)


def test_audio_to_mfcc_pads_clips_shorter_than_the_window(wav_file):
    mfcc = audio_to_mfcc(wav_file(0.5, name="short.wav"))
    assert mfcc.shape == (MFCC_DIM, FRAMES)


def test_audio_to_mfcc_trims_when_a_clip_yields_more_than_frames_frames(wav_file):
    # A 5 s window produces fewer than FRAMES frames, so widen the window to
    # exercise the trimming branch.
    long_clip = audio_to_mfcc(wav_file(12.0, name="long.wav"), duration_s=12.0)
    assert long_clip.shape == (MFCC_DIM, FRAMES)


def test_audio_to_mfcc_only_reads_the_requested_duration(wav_file):
    path = wav_file(12.0, name="long2.wav")
    assert not np.array_equal(
        audio_to_mfcc(path, duration_s=2.0), audio_to_mfcc(path, duration_s=12.0)
    )


def test_audio_to_mfcc_accepts_a_string_path(wav_file):
    assert audio_to_mfcc(str(wav_file())).shape == (MFCC_DIM, FRAMES)


def test_audio_to_mfcc_requires_librosa(monkeypatch, wav_file):
    path = wav_file()
    monkeypatch.setattr(speech_model, "LIBROSA_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="librosa is required"):
        audio_to_mfcc(path)


# ---------- scorer ----------

def test_scorer_scores_mfcc_array_into_unit_range(tmp_path):
    scorer = SpeechScorer(ckpt_path=tmp_path / "missing.pt")
    score = scorer.score_mfcc_array(np.zeros((MFCC_DIM, FRAMES), dtype=np.float32))
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_scorer_is_in_eval_mode_and_deterministic(tmp_path):
    scorer = SpeechScorer(ckpt_path=tmp_path / "missing.pt")
    mfcc = np.random.RandomState(0).randn(MFCC_DIM, FRAMES).astype(np.float32)
    assert scorer.model.training is False
    assert scorer.score_mfcc_array(mfcc) == scorer.score_mfcc_array(mfcc)


def test_scorer_scores_an_audio_file(tmp_path, wav_file):
    scorer = SpeechScorer(ckpt_path=tmp_path / "missing.pt")
    score = scorer.score_audio(wav_file())
    assert 0.0 <= score <= 1.0


def test_scorer_loads_a_checkpoint_when_present(tmp_path):
    ckpt = tmp_path / "speech_cnn.pt"
    trained = SpeechBiomarkerCNN()
    torch.save(trained.state_dict(), ckpt)

    scorer = SpeechScorer(ckpt_path=ckpt)
    for loaded, expected in zip(scorer.model.state_dict().values(), trained.state_dict().values()):
        assert torch.equal(loaded, expected)


def test_scorer_flips_model_logit_so_higher_means_more_normal(tmp_path):
    ckpt = tmp_path / "speech_cnn.pt"
    model = SpeechBiomarkerCNN()
    with torch.no_grad():
        for param in model.classifier.parameters():
            param.zero_()
        model.classifier[-1].bias.fill_(3.0)   # constant "concerning" logit
    torch.save(model.state_dict(), ckpt)

    score = SpeechScorer(ckpt_path=ckpt).score_mfcc_array(
        np.zeros((MFCC_DIM, FRAMES), dtype=np.float32)
    )
    assert score == pytest.approx(1.0 - torch.sigmoid(torch.tensor(3.0)).item(), abs=1e-6)
    assert score < 0.1
