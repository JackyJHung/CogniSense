"""Leakage-firewall sklearn Pipeline factories.

Ported from the research pipeline's `models/pipeline.py`.

The mechanism: every preprocessing step -- imputation, scaling, feature
selection -- is composed INTO the Pipeline. When the outer CV calls
`pipe.fit(X_train, y_train)`, the imputer's medians, the scaler's mean/std and
the selector's k-best statistics are all computed on training rows only. The
fitted transformer is then applied to the test rows unchanged.

Doing the scaling yourself before the split is the single most common way to
leak, and it is invisible in the results: it just makes every number a little
too good. Keeping the steps inside the Pipeline is what prevents it.

Guarded by tests/test_core_no_leakage.py.
"""
from __future__ import annotations

from typing import Literal

from sklearn.feature_selection import SelectKBest, f_classif, f_regression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge, RidgeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler, StandardScaler


def _scaler(kind: str):
    if kind == "standard":
        return StandardScaler()
    if kind == "robust":
        return RobustScaler()
    raise ValueError(f"unknown scaler {kind!r}")


def build_classifier_pipeline(
    scaler: Literal["standard", "robust"] = "standard",
    k_best: int | None = None,
    estimator: str = "logreg",
    random_state: int = 42,
) -> Pipeline:
    """Impute -> scale -> (select) -> classify.

    `k_best=None` keeps all features, which is the right default for the
    behavioral model's 8 features. The research pipeline defaulted to 50
    because a Schaefer-400 connectome has ~80k edges; that default would be
    meaningless here.
    """
    steps: list[tuple[str, object]] = [
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", _scaler(scaler)),
    ]
    if k_best is not None:
        steps.append(("select", SelectKBest(score_func=f_classif, k=k_best)))

    if estimator == "logreg":
        steps.append((
            "clf",
            # `penalty="l2"` is omitted deliberately: it is the default, and
            # passing it explicitly is deprecated from scikit-learn 1.8 and
            # removed in 1.10. Leaving it out is a no-op today and keeps this
            # working on newer scikit-learn.
            LogisticRegression(
                C=1.0, solver="liblinear",
                max_iter=2000, random_state=random_state,
            ),
        ))
    elif estimator == "ridge_clf":
        steps.append(("clf", RidgeClassifier(random_state=random_state)))
    else:
        raise ValueError(f"unknown estimator {estimator!r}")
    return Pipeline(steps)


def build_regressor_pipeline(
    scaler: Literal["standard", "robust"] = "standard",
    k_best: int | None = None,
    random_state: int = 42,
) -> Pipeline:
    steps: list[tuple[str, object]] = [
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", _scaler(scaler)),
    ]
    if k_best is not None:
        steps.append(("select", SelectKBest(score_func=f_regression, k=k_best)))
    steps.append(("reg", Ridge(alpha=1.0, random_state=random_state)))
    return Pipeline(steps)


def safe_k_best(n_features: int, requested_k: int) -> int:
    return min(requested_k, max(1, n_features))
