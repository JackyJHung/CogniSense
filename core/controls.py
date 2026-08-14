"""Negative controls -- the trust audit that runs alongside every result.

Ported from the research pipeline's `models/controls.py`. Three questions, each
one a way for a result to be wrong that a good headline number will not reveal:

  1. permuted_label_control  Is the model learning anything at all, or is the
                             pipeline leaking? Detach labels from people and
                             re-run: performance must collapse to chance.

  2. baseline_comparison     Does the fancy model beat a boring one? A speech
                             CNN that cannot out-predict "age alone" is not
                             earning its complexity or its inference cost.

  3. confound_control        Is the signal the thing we claim? If performance
                             evaporates once a nuisance variable is regressed
                             out, the model was reading the nuisance.

Two things here are stricter than the research original -- see
`_permute_labels_by_group` below and `core.evaluate._residualise_fold`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import roc_auc_score

from core.evaluate import EvalResult
from core.stats import MetricCI, paired_bootstrap_delta

logger = logging.getLogger(__name__)

CHANCE_AUC = 0.5


@dataclass
class ControlResult:
    name: str
    metric: MetricCI
    interpretation: str          # one line of plain English, for the report
    passed: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "metric": self.metric.to_dict(),
            "interpretation": self.interpretation,
            "passed": self.passed,
        }


def _permute_labels_by_group(
    y: np.ndarray, group_ids: np.ndarray, rng: np.random.Generator,
) -> np.ndarray:
    """Shuffle labels BETWEEN groups, keeping each group internally consistent.

    The research version permuted rows directly (`rng.permutation(y)`). For
    repeated-measures data that is the wrong null. A user contributing 60 daily
    rows under one label would have those 60 rows scattered across both classes,
    which destroys the group/label correspondence the splitter depends on and
    produces a null that is not centred on chance.

    Permuting the group->label mapping keeps every person's rows on one label
    and tests exactly the thing we care about: that the model cannot recover a
    label once it has been detached from the person it belongs to.

    Falls back to row-wise permutation when labels vary within a group, since
    the group->label map is then undefined.
    """
    groups, first_idx, inverse = np.unique(
        group_ids, return_index=True, return_inverse=True
    )
    group_labels = y[first_idx]

    # Is each group's label constant? If not, no group->label map exists.
    consistent = all(
        len(set(y[group_ids == g].tolist())) == 1 for g in groups
    )
    if not consistent:
        logger.warning(
            "labels vary within groups; falling back to row-wise permutation"
        )
        return rng.permutation(y)

    return rng.permutation(group_labels)[inverse]


def permuted_label_control(
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
    evaluator: Callable[[np.ndarray, np.ndarray, np.ndarray], EvalResult],
    chance: float = CHANCE_AUC,
    random_state: int = 42,
) -> ControlResult:
    """Re-run with labels detached from people. Expect the CI to cover chance."""
    rng = np.random.default_rng(random_state)
    y_perm = _permute_labels_by_group(np.asarray(y), np.asarray(group_ids), rng)

    res = evaluator(X, y_perm, group_ids)
    m = res.metric

    # The failure this control tests for is DIRECTIONAL. Leakage makes permuted
    # labels predictable, i.e. pushes performance ABOVE chance. Only that is a
    # failure.
    #
    # An interval sitting entirely BELOW chance is a different animal: it is the
    # well-documented negative bias of cross-validated AUC under the null.
    # Partitioning into folds makes the training and test class proportions
    # complementary, so a model that picks up the training fold's prior
    # systematically anti-predicts its test fold. That is an artefact of CV, not
    # evidence of a leak, and it gets more pronounced with fewer groups.
    #
    # The research original tested `ci_low <= chance <= ci_high` and would have
    # reported this benign case as a failure.
    above_chance = m.is_estimable and m.ci_low is not None and m.ci_low > chance

    passed = m.is_estimable and not above_chance

    if not m.is_estimable:
        verdict = "inconclusive -- no interval on the permuted run"
    elif above_chance:
        verdict = (
            "FAILED: permuted labels still predict above chance. The pipeline "
            "is leaking, or the groups are not independent"
        )
    elif m.contains(chance):
        verdict = "as expected: permuted performance is indistinguishable from chance"
    else:
        verdict = (
            "below chance, which is the expected negative bias of "
            "cross-validated AUC under the null rather than a leak -- leakage "
            "would push this above chance"
        )

    return ControlResult(
        name="permuted_label",
        metric=m,
        interpretation=(
            f"permuted-label {m.name or 'metric'} = {m.render()} "
            f"(chance = {chance}); {verdict}"
        ),
        passed=passed,
    )


def baseline_comparison(
    candidate: EvalResult,
    baseline: EvalResult,
    baseline_name: str = "baseline",
    metric_fn: Callable[[np.ndarray, np.ndarray], float] = roc_auc_score,
    random_state: int = 42,
) -> ControlResult:
    """Does `candidate` beat `baseline` by an interval that excludes zero?

    Uses a paired bootstrap over the two models' out-of-fold predictions, which
    requires that both were evaluated on identical rows in identical order.
    """
    if candidate.y_true.shape != baseline.y_true.shape or not np.array_equal(
        candidate.y_true, baseline.y_true
    ):
        raise ValueError(
            "candidate and baseline must be evaluated on the same rows in the "
            "same order for a paired comparison"
        )

    delta = paired_bootstrap_delta(
        candidate.y_true, candidate.y_score, baseline.y_score,
        metric_fn=metric_fn, name="delta", random_state=random_state,
    )

    # Beating the baseline means the whole interval sits above zero.
    beats = delta.is_estimable and delta.ci_low is not None and delta.ci_low > 0

    return ControlResult(
        name="baseline_comparison",
        metric=delta,
        interpretation=(
            f"{baseline_name} {baseline.metric.render()}; "
            f"candidate {candidate.metric.render()}; "
            f"difference {delta.render()} -> "
            + ("beats baseline" if beats else "NOT distinguishable from baseline")
        ),
        passed=beats,
    )


def confound_control(
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
    confounds: np.ndarray,
    confounded_evaluator: Callable[
        [np.ndarray, np.ndarray, np.ndarray, np.ndarray], EvalResult
    ],
    original: EvalResult,
    confound_names: str = "confounds",
    tolerance: float = 0.05,
) -> ControlResult:
    """Regress confounds out per-fold, re-run, and see whether signal survives.

    `confounded_evaluator(X, y, group_ids, confounds)` must residualise INSIDE
    each training fold -- `core.evaluate.evaluate_binary` does, which is what
    makes this control trustworthy rather than decorative.
    """
    res = confounded_evaluator(X, y, group_ids, confounds)

    if not (res.metric.is_estimable and original.metric.is_estimable):
        return ControlResult(
            name="confound_control",
            metric=res.metric,
            interpretation=(
                f"after regressing out {confound_names}: {res.metric.render()}; "
                "inconclusive -- missing interval on one side"
            ),
            passed=False,
        )

    drop = original.metric.value - res.metric.value  # type: ignore[operator]
    survives = res.metric.excludes(CHANCE_AUC) and drop < tolerance

    return ControlResult(
        name="confound_control",
        metric=res.metric,
        interpretation=(
            f"after regressing out {confound_names}: {res.metric.render()} "
            f"(was {original.metric.render()}, drop of {drop:+.3f}) -> "
            + (
                "signal survives"
                if survives
                else "signal does NOT survive; it was largely the confound"
            )
        ),
        passed=survives,
    )


def overall_verdict(controls: list[ControlResult]) -> str:
    """The one mandatory line. Any failed control sinks the whole result."""
    if not controls:
        return "n/a -- no controls were run, so nothing here is trustworthy yet"
    failed = [c.name for c in controls if not c.passed]
    if not failed:
        return f"PASS -- all {len(controls)} negative controls behaved as expected"
    return (
        f"FAIL -- {len(failed)} of {len(controls)} controls failed "
        f"({', '.join(failed)}); headline numbers should not be reported"
    )
