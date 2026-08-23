"""Unit tests for app/ml/behavioral_model.py."""

import numpy as np
import pytest
import torch

from app.ml.behavioral_model import (
    BEHAV_FEATURES,
    BehavioralBiomarkerMLP,
    BehavioralScorer,
    activity_overlap,
    build_behavioral_feature_vector,
    lexical_diversity,
)


# ---------- lexical_diversity ----------

@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_lexical_diversity_of_empty_text_is_zero(text):
    assert lexical_diversity(text) == 0.0


def test_lexical_diversity_all_unique_tokens_is_one():
    assert lexical_diversity("walked the dog") == 1.0


def test_lexical_diversity_counts_repeats_case_insensitively():
    assert lexical_diversity("dog Dog dog cat") == pytest.approx(0.5)


# ---------- activity_overlap ----------

def test_activity_overlap_full_recall():
    assert activity_overlap("walk dog buy groceries", "walk dog buy groceries") == 1.0


def test_activity_overlap_partial_recall():
    # Tokens longer than 2 chars: {walk, dog, buy, groceries}; "walk"/"dog" recalled
    assert activity_overlap("walk dog buy groceries", "walk dog") == pytest.approx(0.5)


def test_activity_overlap_ignores_punctuation_and_case():
    assert activity_overlap("Walk the DOG, buy bread.", "walk dog the buy bread") == 1.0


def test_activity_overlap_ignores_short_tokens():
    # "an" is only 2 chars so it is dropped from both sides
    assert activity_overlap("an apple", "apple") == 1.0


def test_activity_overlap_with_no_plan_is_zero():
    assert activity_overlap("", "walked the dog") == 0.0
    assert activity_overlap("to be", "walked the dog") == 0.0


def test_activity_overlap_with_no_recall_is_zero():
    assert activity_overlap("walk dog", "") == 0.0


# ---------- build_behavioral_feature_vector ----------

def _feature_vector(**overrides):
    kwargs = dict(
        activity_recall_accuracy=0.8,
        association_accuracy=0.6,
        avg_response_latency_ms=1500,
        baseline_latency_ms=1500,
        recalled_text="walked the dog and bought groceries",
        latency_variance=0.1,
        checkin_consistency=0.9,
        speech_biomarker_score=0.75,
    )
    kwargs.update(overrides)
    return build_behavioral_feature_vector(**kwargs)


def test_feature_vector_shape_and_dtype():
    feats = _feature_vector()
    assert feats.shape == (BEHAV_FEATURES,)
    assert feats.dtype == np.float32


def test_feature_vector_positions_carry_expected_values():
    feats = _feature_vector(activity_recall_accuracy=0.4, association_accuracy=0.2,
                            latency_variance=0.3, checkin_consistency=0.5,
                            speech_biomarker_score=0.9)
    assert feats[0] == pytest.approx(0.4)
    assert feats[1] == pytest.approx(0.2)
    assert feats[5] == pytest.approx(0.3)
    assert feats[6] == pytest.approx(0.5)
    assert feats[7] == pytest.approx(0.9)


def test_latency_z_is_relative_to_the_users_own_baseline():
    same = _feature_vector(avg_response_latency_ms=1500, baseline_latency_ms=1500)
    slower = _feature_vector(avg_response_latency_ms=3000, baseline_latency_ms=1500)
    faster = _feature_vector(avg_response_latency_ms=750, baseline_latency_ms=1500)

    assert same[2] == pytest.approx(0.0)
    assert slower[2] == pytest.approx(1.0)
    assert faster[2] == pytest.approx(-0.5)


def test_latency_z_is_clipped_to_model_range():
    assert _feature_vector(avg_response_latency_ms=100_000, baseline_latency_ms=1000)[2] == 4.0
    assert _feature_vector(avg_response_latency_ms=0, baseline_latency_ms=1000)[2] == pytest.approx(-1.0)


def test_latency_z_is_zero_without_a_baseline():
    assert _feature_vector(avg_response_latency_ms=5000, baseline_latency_ms=0)[2] == 0.0


def test_word_count_is_normalised_and_capped():
    short = _feature_vector(recalled_text="walked")
    typical = _feature_vector(recalled_text=" ".join(["word"] * 30))
    verbose = _feature_vector(recalled_text=" ".join(["word"] * 300))

    assert short[4] == pytest.approx(1 / 30)
    assert typical[4] == pytest.approx(1.0)
    assert verbose[4] == 2.0


def test_lexical_diversity_feature_matches_helper():
    text = "dog dog cat"
    assert _feature_vector(recalled_text=text)[3] == pytest.approx(lexical_diversity(text))


# ---------- model + scorer ----------

def test_mlp_forward_shape():
    model = BehavioralBiomarkerMLP()
    out = model(torch.zeros(4, BEHAV_FEATURES))
    assert out.shape == (4, 1)


def test_mlp_accepts_custom_input_width():
    model = BehavioralBiomarkerMLP(in_features=3)
    assert model(torch.zeros(2, 3)).shape == (2, 1)


def test_scorer_returns_probability_in_unit_range(tmp_path):
    scorer = BehavioralScorer(ckpt_path=tmp_path / "missing.pt")
    score = scorer.score(_feature_vector())
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_scorer_is_deterministic_and_in_eval_mode(tmp_path):
    scorer = BehavioralScorer(ckpt_path=tmp_path / "missing.pt")
    feats = _feature_vector()
    assert scorer.model.training is False
    assert scorer.score(feats) == scorer.score(feats)


def test_scorer_loads_a_checkpoint_when_present(tmp_path):
    ckpt = tmp_path / "behavioral_mlp.pt"
    trained = BehavioralBiomarkerMLP()
    with torch.no_grad():
        for param in trained.parameters():
            param.fill_(0.05)
    torch.save(trained.state_dict(), ckpt)

    scorer = BehavioralScorer(ckpt_path=ckpt)
    for loaded, expected in zip(scorer.model.parameters(), trained.parameters()):
        assert torch.equal(loaded, expected)


def test_scorer_flips_model_logit_so_higher_means_more_normal(tmp_path):
    """Model logits mean 'concerning'; the scorer must return 1 - sigmoid(logit)."""
    ckpt = tmp_path / "behavioral_mlp.pt"
    model = BehavioralBiomarkerMLP()
    with torch.no_grad():
        for param in model.parameters():
            param.zero_()
        # Final bias only => constant logit of +4 (very concerning)
        list(model.parameters())[-1].fill_(4.0)
    torch.save(model.state_dict(), ckpt)

    score = BehavioralScorer(ckpt_path=ckpt).score(_feature_vector())
    assert score == pytest.approx(1.0 - torch.sigmoid(torch.tensor(4.0)).item(), abs=1e-6)
    assert score < 0.05
