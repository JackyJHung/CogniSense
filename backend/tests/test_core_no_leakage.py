"""The leakage firewall. These tests MUST fail if test-fold data touches training.

Ported from the research pipeline's tests/test_no_leakage.py, which guarded the
code now living in core/. The adversarial fixture is the same idea, retargeted
to this app's data shape: one USER contributing many daily rows, rather than one
patient contributing several repeat-tracked connectomes.

The last two tests are new. The research version's "deliberately do it wrong"
test only asserted that a scaler fitted on all of X has the mean of all of X --
trivially true, and it demonstrated nothing about leakage. Here we do the real
demonstration: split the same data by row instead of by user and watch the AUC
inflate.
"""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

from core.controls import permuted_label_control
from core.evaluate import evaluate_binary
from core.pipelines import build_classifier_pipeline
from core.splits import assert_no_leakage, grouped_nested_splits


def _repeated_measures_dataset(n_users=40, days=8, n_features=8, seed=0):
    """Each user contributes `days` rows sharing one label.

    A large per-user offset and a small per-day jitter make the user far easier
    to identify than the label -- the adversarial case for leakage, and a fair
    caricature of real check-in data.
    """
    rng = np.random.default_rng(seed)
    rows, ids, ys = [], [], []
    for u in range(n_users):
        y = int(rng.integers(0, 2))
        base = rng.normal(loc=0.6 * y - 0.3, scale=1.0, size=n_features)
        for _ in range(days):
            rows.append(base + rng.normal(0, 0.05, size=n_features))
            ids.append(f"U-{u:03d}")
            ys.append(y)
    return np.vstack(rows), np.array(ids), np.array(ys)


def test_group_split_keeps_each_user_on_one_side():
    X, ids, y = _repeated_measures_dataset()
    for fold in grouped_nested_splits(
        ids, y=y, outer_folds=5, inner_folds=2, stratify=True, random_state=0,
    ):
        assert_no_leakage(ids, fold.train_idx, fold.test_idx)


def test_group_split_holds_under_many_seeds():
    X, ids, y = _repeated_measures_dataset()
    for seed in range(30):
        for fold in grouped_nested_splits(
            ids, y=y, outer_folds=5, inner_folds=2, random_state=seed,
        ):
            assert_no_leakage(ids, fold.train_idx, fold.test_idx)


def test_scaler_is_fitted_on_the_training_fold_only():
    X, ids, y = _repeated_measures_dataset()
    full_mean = StandardScaler().fit(X).mean_

    differs_at_least_once = False
    for fold in grouped_nested_splits(
        ids, y=y, outer_folds=5, inner_folds=2, random_state=0,
    ):
        pipe: Pipeline = build_classifier_pipeline(random_state=0)
        pipe.fit(X[fold.train_idx], y[fold.train_idx])
        if not np.allclose(pipe.named_steps["scaler"].mean_, full_mean, atol=1e-9):
            differs_at_least_once = True

    assert differs_at_least_once, (
        "the scaler's mean_ matched the full-dataset mean on every fold; "
        "that is the signature of fitting on test data"
    )


def test_feature_selection_is_fitted_on_the_training_fold_only():
    X, ids, y = _repeated_measures_dataset(n_features=20)
    full = Pipeline([
        ("scaler", StandardScaler()),
        ("sel", SelectKBest(score_func=f_classif, k=5)),
    ]).fit(X, y)
    full_idx = set(np.where(full.named_steps["sel"].get_support())[0].tolist())

    any_diff = False
    for fold in grouped_nested_splits(
        ids, y=y, outer_folds=5, inner_folds=2, random_state=0,
    ):
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("sel", SelectKBest(score_func=f_classif, k=5)),
        ]).fit(X[fold.train_idx], y[fold.train_idx])
        fold_idx = set(np.where(pipe.named_steps["sel"].get_support())[0].tolist())
        if fold_idx != full_idx:
            any_diff = True
            break

    assert any_diff, (
        "feature selection chose the same features on every fold as on the "
        "full dataset; that is the signature of leakage"
    )


def test_row_level_splitting_inflates_auc_relative_to_user_level():
    """The demonstration the research version was missing.

    Same data, same estimator. Splitting by row lets a user's Monday train the
    model that scores their Tuesday, so the model is rewarded for recognising
    the person. The inflation should be large and one-directional.
    """
    X, ids, y = _repeated_measures_dataset(n_users=40, days=8, seed=1)

    honest = evaluate_binary(
        X, y, ids,
        pipeline_factory=lambda: build_classifier_pipeline(random_state=0),
        target="grouped", outer_folds=5, n_bootstrap=300, random_state=0,
    )

    # The leaky alternative: ignore the user entirely and split rows at random.
    leaky_oof = np.full(y.shape[0], np.nan)
    for tr, te in StratifiedKFold(n_splits=5, shuffle=True, random_state=0).split(X, y):
        pipe = build_classifier_pipeline(random_state=0)
        pipe.fit(X[tr], y[tr])
        leaky_oof[te] = pipe.predict_proba(X[te])[:, 1]
    leaky_auc = roc_auc_score(y, leaky_oof)

    assert leaky_auc > honest.metric.value, (
        f"row-level splitting ({leaky_auc:.3f}) should score higher than "
        f"user-level splitting ({honest.metric.value:.3f}) on repeated-measures "
        f"data; if it does not, the fixture is not adversarial enough"
    )
    assert leaky_auc - honest.metric.value > 0.05, (
        f"expected a substantial inflation, got {leaky_auc - honest.metric.value:+.3f}"
    )


def test_permuted_label_control_passes_on_an_honest_pipeline():
    """Guards the direction of the permuted-label check.

    An honest pipeline must not score ABOVE chance once labels are detached
    from users. Landing below chance is the known negative bias of CV under the
    null and must not be reported as a failure.
    """
    X, ids, y = _repeated_measures_dataset(n_users=40, days=8, seed=2)

    def evaluator(Xa, ya, ga):
        return evaluate_binary(
            Xa, ya, ga,
            pipeline_factory=lambda: build_classifier_pipeline(random_state=0),
            target="perm", outer_folds=5, n_bootstrap=300, random_state=0,
        )

    result = permuted_label_control(X, y, ids, evaluator, random_state=0)

    assert result.passed, f"honest pipeline failed its own control: {result.interpretation}"
    assert result.metric.ci_low is not None
    assert result.metric.ci_low <= 0.5, (
        "permuted labels scored above chance -- that is leakage"
    )


def test_grouped_splits_reject_too_few_groups():
    X, ids, y = _repeated_measures_dataset(n_users=3, days=5)
    with pytest.raises(ValueError, match="cannot make"):
        list(grouped_nested_splits(ids, y=y, outer_folds=5, inner_folds=2))
