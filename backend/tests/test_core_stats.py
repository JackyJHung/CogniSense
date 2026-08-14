"""Uncertainty semantics: the rules the rest of the app relies on."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

from core.stats import (
    MetricCI,
    bootstrap_ci,
    bootstrap_delta_ci,
    bootstrap_stat_ci,
    paired_bootstrap_delta,
)


def test_a_value_without_an_interval_renders_visibly_incomplete():
    """A bare point estimate must never look like a finished result."""
    assert MetricCI(value=0.812).render() == "0.812 [CI n/a]"
    assert MetricCI().render() == "n/a"
    assert MetricCI(value=0.812, ci_low=0.75, ci_high=0.87).render() == "0.812 [0.750, 0.870]"


def test_excludes_is_false_when_the_interval_is_unknown():
    """Absence of evidence must not read as a positive finding."""
    assert MetricCI(value=0.9).excludes(0.5) is False
    assert MetricCI(value=0.9).contains(0.5) is False
    assert MetricCI(value=0.9, ci_low=0.8, ci_high=0.95).excludes(0.5) is True
    assert MetricCI(value=0.6, ci_low=0.4, ci_high=0.8).contains(0.5) is True


def test_too_few_observations_yields_no_interval():
    m = bootstrap_stat_ci([0.8, 0.7])
    assert m.value is not None          # point estimate is still reported
    assert m.ci_low is None             # but no interval is invented
    assert "below minimum" in m.note

    empty = bootstrap_stat_ci([])
    assert empty.value is None
    assert empty.note == "no observations"


def test_stat_ci_brackets_the_point_estimate():
    values = [0.80, 0.75, 0.82, 0.79, 0.81, 0.77, 0.80, 0.78]
    m = bootstrap_stat_ci(values, random_state=0)
    assert m.ci_low <= m.value <= m.ci_high
    assert m.n == len(values)


def test_delta_detects_a_real_drop_and_excludes_zero():
    baseline = [0.80, 0.82, 0.79, 0.81, 0.80, 0.83, 0.78, 0.81]
    recent = [0.50, 0.48, 0.52, 0.49, 0.51, 0.47, 0.50, 0.49]
    d = bootstrap_delta_ci(baseline, recent, relative=True, random_state=0)
    assert d.value < 0
    assert d.excludes(0.0), "a drop this clean should exclude zero"


def test_delta_on_noisy_data_spans_zero():
    """The case that used to trigger a false warning.

    A mean drop of roughly 20% measured on wildly variable days is not
    distinguishable from noise, and the interval must say so.
    """
    rng = np.random.default_rng(0)
    baseline = list(rng.uniform(0.2, 0.95, size=6))
    recent = list(rng.uniform(0.15, 0.8, size=6))
    d = bootstrap_delta_ci(baseline, recent, relative=True, random_state=0)
    assert not d.excludes(0.0), "noisy data must not produce a confident change"


def test_paired_bootstrap_is_tighter_than_treating_models_as_independent():
    """Why the paired comparison replaced the research pipeline's approximation.

    Two models scored on the SAME rows have correlated errors. Resampling those
    rows once and evaluating both on the resample cancels the shared variance,
    so the interval on the difference is narrower than the naive 'width of the
    widest input CI' the original used.
    """
    rng = np.random.default_rng(0)
    n = 400
    y = rng.integers(0, 2, n)
    signal = y + rng.normal(0, 1.0, n)
    strong = signal + rng.normal(0, 0.25, n)
    weak = signal + rng.normal(0, 1.4, n)

    a = bootstrap_ci(y, strong, roc_auc_score, random_state=0)
    b = bootstrap_ci(y, weak, roc_auc_score, random_state=0)
    delta = paired_bootstrap_delta(y, strong, weak, roc_auc_score, random_state=0)

    naive_width = max(a.ci_high - a.ci_low, b.ci_high - b.ci_low)
    paired_width = delta.ci_high - delta.ci_low

    assert paired_width < naive_width, (
        f"paired interval ({paired_width:.4f}) should be tighter than the naive "
        f"one ({naive_width:.4f})"
    )
    assert delta.value > 0 and delta.excludes(0.0)


def test_bootstrap_ci_survives_degenerate_resamples():
    """roc_auc_score raises on a single-class resample; that must not abort."""
    y = np.array([0] + [1] * 19)
    score = np.linspace(0, 1, 20)
    m = bootstrap_ci(y, score, roc_auc_score, n=200, random_state=0)
    assert m.value is not None
    assert m.ci_low is not None
