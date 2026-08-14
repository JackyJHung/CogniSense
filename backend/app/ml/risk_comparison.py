"""
Risk comparison service.

Takes a user's recent behavioral scores and returns a RiskComparisonOut payload
that compares them against research benchmarks (age, gender, race). This is
what powers the "how am I doing vs. my demographic peers" report and the
attention-warning trigger.

KEY DESIGN CHOICE
-----------------
We do NOT claim to predict Alzheimer's. We produce two outputs:
  1. user_recent_avg_score  -- the user's own rolling daily cognitive score
                               from the PyTorch models. A drop over time in
                               THIS metric, not the absolute number, is the
                               concerning signal.
  2. peer_expected_prevalence -- population-level research benchmark, from
                                 Alzheimer's Association / CDC / Lancet data,
                                 for context only.

The attention warning fires when the user's *trajectory* is downward, not
because their raw score is "low." This avoids stigmatizing users whose
baselines are lower for cultural / educational reasons unrelated to AD.

WHAT THE MERGE CHANGED
----------------------
The trajectory test used to compare two bare means against two fixed
thresholds -- a 20% relative drop, or an absolute score below 0.35. Neither
carried any notion of how noisy the underlying daily scores were. A user with
four erratic check-ins and a user with forty steady ones would trip the same
warning off the same point estimate, and daily cognitive scores are noisy:
sleep, mood and time-of-day all move them independently of cognition.

Both tests now run through `core.stats`, and each requires its interval to
clear the threshold, not just its midpoint:

  - relative drop: the 95% CI on the change must exclude zero
  - absolute floor: the whole CI must sit below the floor

A 20% drop that could as easily be a 5% rise no longer tells somebody they may
be declining. When there is not yet enough data to separate those, the result
is reported as inconclusive rather than as reassurance -- see `TrajectoryResult
.inconclusive`, which the report surfaces explicitly.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import random

import numpy as np

from app.data.research_benchmarks import (
    compute_benchmark,
    LANCET_2024_RISK_FACTORS,
    NON_DIAGNOSTIC_DISCLAIMER,
)
from core.stats import MetricCI, bootstrap_delta_ci, bootstrap_stat_ci


# Thresholds for triggering the attention warning. Tunable.
WARNING_SCORE_DROP_THRESHOLD = 0.20       # 20% drop vs. user's own baseline
WARNING_ABSOLUTE_FLOOR = 0.35             # OR absolute score below 0.35
MINIMUM_CHECKINS_FOR_WARNING = 14         # Need 2+ weeks of data before warning


@dataclass
class TrajectoryResult:
    current: MetricCI          # mean of recent daily scores, with CI
    baseline: MetricCI         # mean of the user's earlier scores, with CI
    change: MetricCI           # relative change vs. baseline, with CI
    elevated_concern: bool
    reason: Optional[str]
    inconclusive: bool         # too few / too noisy to call either way
    inconclusive_reason: Optional[str] = None

    # Backwards-compatible scalar views, so existing callers and the API
    # response model keep working unchanged.
    @property
    def current_avg(self) -> float:
        return round(self.current.value or 0.0, 3)

    @property
    def baseline_avg(self) -> float:
        return round(self.baseline.value or 0.0, 3)

    @property
    def pct_change(self) -> float:
        return round(self.change.value or 0.0, 3)


def analyze_trajectory(
    recent_scores: list[float],
    baseline_scores: list[float],
    total_checkins: int,
    random_state: int = 42,
) -> TrajectoryResult:
    """
    recent_scores: last ~7 daily cognitive scores (0..1)
    baseline_scores: user's earliest ~7-14 daily scores (0..1)

    Returns a TrajectoryResult whose `elevated_concern` flag is only set when
    the evidence supports it -- see the module docstring.
    """
    current = bootstrap_stat_ci(
        recent_scores, name="recent_avg", random_state=random_state
    )
    baseline = bootstrap_stat_ci(
        baseline_scores, name="baseline_avg", random_state=random_state
    )
    change = bootstrap_delta_ci(
        baseline_scores, recent_scores, relative=True,
        name="relative_change", random_state=random_state,
    )

    elevated = False
    reason: Optional[str] = None
    inconclusive = False
    inconclusive_reason: Optional[str] = None

    if total_checkins < MINIMUM_CHECKINS_FOR_WARNING:
        inconclusive = True
        inconclusive_reason = (
            f"Only {total_checkins} check-ins so far. We need at least "
            f"{MINIMUM_CHECKINS_FOR_WARNING} before reading anything into a trend."
        )
    elif not change.is_estimable:
        inconclusive = True
        inconclusive_reason = (
            "Not enough scored days on both sides to compare your recent scores "
            "against your earlier baseline yet."
        )
    else:
        real_drop = (
            change.value is not None
            and change.value <= -WARNING_SCORE_DROP_THRESHOLD
            and change.excludes(0.0)          # interval clears zero
        )
        # Whole interval below the floor, not just the midpoint.
        real_floor = (
            current.is_estimable
            and current.ci_high is not None
            and current.ci_high < WARNING_ABSOLUTE_FLOOR
        )

        if real_drop:
            elevated = True
            reason = (
                f"Your average daily cognitive score has dropped about "
                f"{abs(change.value) * 100:.0f}% compared with your own earlier "
                f"baseline (95% CI {change.ci_low * 100:+.0f}% to "
                f"{change.ci_high * 100:+.0f}%). The whole range is below zero, "
                f"so this looks like a real change rather than day-to-day noise."
            )
        elif real_floor:
            elevated = True
            reason = (
                f"Your recent daily cognitive scores have been consistently low "
                f"(average {current.value:.2f} out of 1.0, 95% CI "
                f"{current.ci_low:.2f} to {current.ci_high:.2f}), with the whole "
                f"range below {WARNING_ABSOLUTE_FLOOR}."
            )
        elif (
            change.value is not None
            and change.value <= -WARNING_SCORE_DROP_THRESHOLD
        ):
            # Point estimate looks bad but the interval spans zero. Say so
            # rather than either warning or implying all-clear.
            inconclusive = True
            inconclusive_reason = (
                f"Your recent average is about {abs(change.value) * 100:.0f}% below "
                f"your earlier baseline, but your day-to-day scores vary enough "
                f"that this could still be normal fluctuation (95% CI "
                f"{change.ci_low * 100:+.0f}% to {change.ci_high * 100:+.0f}%). "
                f"Keep checking in -- more days will make this clearer."
            )

    return TrajectoryResult(
        current=current,
        baseline=baseline,
        change=change,
        elevated_concern=elevated,
        reason=reason,
        inconclusive=inconclusive,
        inconclusive_reason=inconclusive_reason,
    )


def personalized_suggestions(
    age: int,
    elevated_concern: bool,
    n: int = 4,
) -> list[str]:
    """
    Pick n suggestions from the Lancet 2024 modifiable risk factors, biased
    toward life-stage-appropriate factors.
    """
    if age < 45:
        stage_priority = ["early life (<18)", "across life"]
    elif age < 65:
        stage_priority = ["midlife (45-65)", "midlife", "midlife+", "midlife (40-65)", "across life"]
    else:
        stage_priority = ["later life (65+)", "later life", "midlife+", "across life"]

    priority = [
        f for f in LANCET_2024_RISK_FACTORS
        if any(stage in f["life_stage"] for stage in stage_priority)
    ]
    rest = [f for f in LANCET_2024_RISK_FACTORS if f not in priority]

    # If elevated concern, prepend social-engagement + physical activity (strong universal recs)
    suggestions: list[str] = []
    if elevated_concern:
        suggestions.append(
            "Schedule an appointment with your primary care doctor to discuss memory "
            "concerns. Early evaluation leads to better options and support."
        )

    random.shuffle(priority)

    def _label(factor: dict) -> str:
        # Prefer the user-facing action-oriented label; fall back to the
        # Lancet risk-factor name only if `display_label` is missing.
        return factor.get("display_label") or factor["name"]

    for factor in priority[: max(0, n - len(suggestions))]:
        suggestions.append(f"{_label(factor)}: {factor['suggestion']}")

    # Top up from rest if needed
    for factor in rest:
        if len(suggestions) >= n + (1 if elevated_concern else 0):
            break
        suggestions.append(f"{_label(factor)}: {factor['suggestion']}")

    return suggestions


def build_risk_comparison(
    age: int,
    gender: str,
    race: str,
    recent_scores: list[float],
    baseline_scores: list[float],
    total_checkins: int,
) -> dict:
    """
    Returns a dict ready to be serialized as RiskComparisonOut.
    """
    traj = analyze_trajectory(recent_scores, baseline_scores, total_checkins)
    bench = compute_benchmark(age, gender, race)  # type: ignore[arg-type]
    suggestions = personalized_suggestions(age, traj.elevated_concern)

    return {
        "user_recent_avg_score": traj.current_avg,
        "user_recent_avg_ci_low": traj.current.ci_low,
        "user_recent_avg_ci_high": traj.current.ci_high,
        "trajectory_change_pct": (
            None if traj.change.value is None else round(traj.change.value * 100, 1)
        ),
        "trajectory_change_ci_low_pct": (
            None if traj.change.ci_low is None else round(traj.change.ci_low * 100, 1)
        ),
        "trajectory_change_ci_high_pct": (
            None if traj.change.ci_high is None else round(traj.change.ci_high * 100, 1)
        ),
        "n_scored_days": traj.current.n,
        "peer_expected_prevalence_pct": round(bench.combined_expected_prevalence * 100, 2),
        "scd_peer_prevalence_pct": round(bench.scd_peer_prevalence * 100, 2),
        "elevated_concern": traj.elevated_concern,
        "concern_reason": traj.reason,
        "inconclusive": traj.inconclusive,
        "inconclusive_reason": traj.inconclusive_reason,
        "suggestions": suggestions,
        "citations": bench.citations,
        "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
    }
