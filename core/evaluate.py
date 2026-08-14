"""Nested-CV evaluation producing out-of-fold predictions and CI-bearing metrics.

Ported from the research pipeline's `models/classify.py`, with one substantive
fix carried over from a TODO left open there.

THE FIX. The research version's confound check called `residualise(X, confounds,
train_idx=np.arange(X.shape[0]))` -- fitting the confound regression on every
row, test rows included, then evaluating on those same rows. That leaks, and it
leaks in the direction that makes the control look like it passed. The comment
in `models/controls.py` acknowledged it:

    # TODO: move residualise() inside the evaluator's per-fold loop.

Here it IS inside the loop: `_residualise_fold` fits on training rows only and
applies the train-fitted regression to both sides. Passing `confounds=` to
`evaluate_binary` is therefore safe to report.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import brier_score_loss, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline

from core.splits import grouped_nested_splits
from core.stats import MetricCI, bootstrap_ci


@dataclass
class EvalResult:
    """Out-of-fold predictions plus every metric derived from them."""

    target: str
    metric: MetricCI                      # primary discrimination metric
    calibration: MetricCI | None = None   # Brier score; lower is better
    y_true: np.ndarray = field(default_factory=lambda: np.array([]))
    y_score: np.ndarray = field(default_factory=lambda: np.array([]))
    y_pred: np.ndarray = field(default_factory=lambda: np.array([]))
    n_rows: int = 0
    n_groups: int = 0
    outer_folds: int = 0

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "metric": self.metric.to_dict(),
            "calibration": self.calibration.to_dict() if self.calibration else None,
            "n_rows": self.n_rows,
            "n_groups": self.n_groups,
            "outer_folds": self.outer_folds,
        }


def _residualise_fold(
    X: np.ndarray,
    confounds: np.ndarray,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit X ~ confounds on TRAIN ONLY; return residuals for train and test.

    The test residuals are computed with the train-fitted regression, so no
    test-row information reaches the transform.
    """
    reg = LinearRegression().fit(confounds[train_idx], X[train_idx])
    X_tr = X[train_idx] - reg.predict(confounds[train_idx])
    X_te = X[test_idx] - reg.predict(confounds[test_idx])
    return X_tr, X_te


def evaluate_binary(
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
    pipeline_factory: Callable[[], Pipeline],
    target: str = "",
    confounds: np.ndarray | None = None,
    outer_folds: int = 5,
    inner_folds: int = 3,
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> EvalResult:
    """Group-level nested CV -> AUC and Brier, each with a 95% CI.

    `pipeline_factory` is a no-arg callable returning a FRESH pipeline; one is
    built per outer fold so no fitted state crosses folds.

    `confounds` (n_rows, n_confounds), when given, is regressed out of X inside
    each fold before fitting -- see the module docstring.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    group_ids = np.asarray(group_ids)

    oof_score = np.full(y.shape[0], np.nan, dtype=float)
    oof_pred = np.full(y.shape[0], -1, dtype=int)
    n_folds_run = 0

    for fold in grouped_nested_splits(
        group_ids, y=y, outer_folds=outer_folds, inner_folds=inner_folds,
        stratify=True, random_state=random_state,
    ):
        if confounds is not None:
            X_tr, X_te = _residualise_fold(
                X, np.asarray(confounds, dtype=float),
                fold.train_idx, fold.test_idx,
            )
        else:
            X_tr, X_te = X[fold.train_idx], X[fold.test_idx]

        pipe = pipeline_factory()
        pipe.fit(X_tr, y[fold.train_idx])

        if hasattr(pipe, "predict_proba"):
            score = pipe.predict_proba(X_te)[:, 1]
        else:
            raw = pipe.decision_function(X_te)
            span = float(np.ptp(raw))
            score = (raw - raw.min()) / max(1e-9, span)

        oof_score[fold.test_idx] = score
        oof_pred[fold.test_idx] = (score >= 0.5).astype(int)
        n_folds_run += 1

    if np.any(np.isnan(oof_score)):
        n_missing = int(np.isnan(oof_score).sum())
        raise RuntimeError(
            f"{n_missing} rows never landed in a test fold; check group sizes"
        )

    auc = bootstrap_ci(
        y, oof_score, roc_auc_score, name="AUC",
        n=n_bootstrap, random_state=random_state,
    )
    brier = bootstrap_ci(
        y, oof_score, brier_score_loss, name="Brier",
        n=n_bootstrap, random_state=random_state,
    )

    return EvalResult(
        target=target, metric=auc, calibration=brier,
        y_true=y, y_score=oof_score, y_pred=oof_pred,
        n_rows=int(y.shape[0]),
        n_groups=len(set(group_ids.tolist())),
        outer_folds=n_folds_run,
    )


def evaluate_multiclass(
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
    pipeline_factory: Callable[[], Pipeline],
    target: str = "",
    outer_folds: int = 5,
    inner_folds: int = 3,
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> EvalResult:
    """Multiclass variant scored with macro-F1."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    group_ids = np.asarray(group_ids)

    oof_pred = np.full(y.shape[0], -1, dtype=int)
    n_folds_run = 0

    for fold in grouped_nested_splits(
        group_ids, y=y, outer_folds=outer_folds, inner_folds=inner_folds,
        stratify=True, random_state=random_state,
    ):
        pipe = pipeline_factory()
        pipe.fit(X[fold.train_idx], y[fold.train_idx])
        oof_pred[fold.test_idx] = pipe.predict(X[fold.test_idx])
        n_folds_run += 1

    if np.any(oof_pred < 0):
        raise RuntimeError("some rows never landed in a test fold")

    def macro_f1(yt: np.ndarray, yp: np.ndarray) -> float:
        return f1_score(yt, yp, average="macro")

    f1 = bootstrap_ci(
        y, oof_pred, macro_f1, name="macro_F1",
        n=n_bootstrap, random_state=random_state,
    )
    return EvalResult(
        target=target, metric=f1, calibration=None,
        y_true=y, y_score=oof_pred.astype(float), y_pred=oof_pred,
        n_rows=int(y.shape[0]),
        n_groups=len(set(group_ids.tolist())),
        outer_folds=n_folds_run,
    )
