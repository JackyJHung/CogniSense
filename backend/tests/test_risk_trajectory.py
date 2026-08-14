"""The attention warning must fire on evidence, not on a threshold crossing.

This is the user-visible consequence of the merge. Before, `analyze_trajectory`
compared two bare means against a fixed 20% threshold; anyone whose noisy recent
average happened to land 20% below their noisy baseline was told they may be
declining. These tests pin the new behaviour: a warning requires the interval
on the change to clear zero, and when it does not, the result is reported as
inconclusive rather than as an all-clear.
"""
from __future__ import annotations

import numpy as np

from app.ml.risk_comparison import (
    MINIMUM_CHECKINS_FOR_WARNING,
    analyze_trajectory,
    build_risk_comparison,
)


STABLE_BASELINE = [0.80, 0.82, 0.79, 0.81, 0.80, 0.83, 0.78, 0.81, 0.80, 0.79]


def test_clear_sustained_drop_raises_concern():
    recent = [0.52, 0.50, 0.54, 0.51, 0.49, 0.53, 0.50, 0.52]
    t = analyze_trajectory(
        recent_scores=recent, baseline_scores=STABLE_BASELINE, total_checkins=40,
    )

    assert t.elevated_concern is True
    assert t.inconclusive is False
    assert t.reason is not None
    assert "95% CI" in t.reason
    assert t.change.excludes(0.0)


def test_noisy_apparent_drop_is_inconclusive_not_a_warning():
    """The false-positive case the old threshold logic produced."""
    rng = np.random.default_rng(3)
    baseline = list(rng.uniform(0.30, 0.95, size=8))
    recent = list(rng.uniform(0.20, 0.80, size=8))
    t = analyze_trajectory(
        recent_scores=recent, baseline_scores=baseline, total_checkins=40,
    )

    if t.change.value is not None and t.change.value <= -0.20:
        # Point estimate crosses the old threshold; the interval must save us.
        assert t.elevated_concern is False, (
            "a drop this noisy must not trigger a warning"
        )
        assert t.inconclusive is True
        assert t.inconclusive_reason is not None


def test_too_few_checkins_is_inconclusive_regardless_of_scores():
    recent = [0.20, 0.18, 0.22]
    t = analyze_trajectory(
        recent_scores=recent, baseline_scores=STABLE_BASELINE, total_checkins=5,
    )

    assert t.elevated_concern is False
    assert t.inconclusive is True
    assert str(MINIMUM_CHECKINS_FOR_WARNING) in (t.inconclusive_reason or "")


def test_stable_scores_produce_neither_warning_nor_inconclusive():
    recent = [0.79, 0.81, 0.80, 0.82, 0.78, 0.80, 0.81, 0.79]
    t = analyze_trajectory(
        recent_scores=recent, baseline_scores=STABLE_BASELINE, total_checkins=40,
    )

    assert t.elevated_concern is False
    assert t.inconclusive is False
    assert t.change.contains(0.0), "stable scores should span zero change"


def test_consistently_low_scores_need_the_whole_interval_below_the_floor():
    """The absolute-floor rule, tightened the same way as the drop rule."""
    very_low = [0.20, 0.22, 0.19, 0.21, 0.20, 0.18, 0.22, 0.20]
    t = analyze_trajectory(
        recent_scores=very_low, baseline_scores=very_low, total_checkins=40,
    )
    assert t.elevated_concern is True
    assert t.current.ci_high < 0.35

    # Straddling the floor: mean is below it, but the interval is not.
    straddling = [0.10, 0.60, 0.15, 0.55, 0.20, 0.62, 0.12, 0.58]
    t2 = analyze_trajectory(
        recent_scores=straddling, baseline_scores=straddling, total_checkins=40,
    )
    assert t2.current.ci_high > 0.35
    assert t2.elevated_concern is False


def test_payload_carries_intervals_and_the_inconclusive_flag():
    payload = build_risk_comparison(
        age=72, gender="female", race="white",
        recent_scores=[0.52, 0.50, 0.54, 0.51, 0.49, 0.53, 0.50, 0.52],
        baseline_scores=STABLE_BASELINE,
        total_checkins=40,
    )

    for key in (
        "user_recent_avg_score",
        "user_recent_avg_ci_low",
        "user_recent_avg_ci_high",
        "trajectory_change_pct",
        "trajectory_change_ci_low_pct",
        "trajectory_change_ci_high_pct",
        "inconclusive",
        "n_scored_days",
    ):
        assert key in payload, f"payload is missing {key}"

    assert payload["elevated_concern"] is True
    assert payload["user_recent_avg_ci_low"] is not None
    assert payload["trajectory_change_pct"] < 0
    assert payload["disclaimer"]
