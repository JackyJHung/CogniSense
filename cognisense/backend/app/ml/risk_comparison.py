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
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import random

from app.data.research_benchmarks import (
    compute_benchmark,
    LANCET_2024_RISK_FACTORS,
    NON_DIAGNOSTIC_DISCLAIMER,
)


# Thresholds for triggering the attention warning. Tunable.
WARNING_SCORE_DROP_THRESHOLD = 0.20       # 20% drop vs. user's own baseline
WARNING_ABSOLUTE_FLOOR = 0.35             # OR absolute score below 0.35
MINIMUM_CHECKINS_FOR_WARNING = 14         # Need 2+ weeks of data before warning


@dataclass
class TrajectoryResult:
    current_avg: float
    baseline_avg: float
    pct_change: float
    elevated_concern: bool
    reason: Optional[str]


def analyze_trajectory(
    recent_scores: list[float],
    baseline_scores: list[float],
    total_checkins: int,
) -> TrajectoryResult:
    """
    recent_scores: last ~7 daily cognitive scores (0..1)
    baseline_scores: user's earliest ~7-14 daily scores (0..1)

    Returns a TrajectoryResult with elevated_concern flag.
    """
    current_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 0.0
    baseline_avg = sum(baseline_scores) / len(baseline_scores) if baseline_scores else current_avg

    if baseline_avg == 0:
        pct_change = 0.0
    else:
        pct_change = (current_avg - baseline_avg) / baseline_avg

    elevated = False
    reason: Optional[str] = None

    if total_checkins >= MINIMUM_CHECKINS_FOR_WARNING:
        if pct_change <= -WARNING_SCORE_DROP_THRESHOLD:
            elevated = True
            reason = (
                f"Your average daily cognitive score has dropped roughly "
                f"{abs(pct_change)*100:.0f}% compared to your own earlier baseline."
            )
        elif current_avg < WARNING_ABSOLUTE_FLOOR:
            elevated = True
            reason = (
                f"Your recent daily cognitive scores have been consistently low "
                f"(current average: {current_avg:.2f} out of 1.0)."
            )

    return TrajectoryResult(
        current_avg=round(current_avg, 3),
        baseline_avg=round(baseline_avg, 3),
        pct_change=round(pct_change, 3),
        elevated_concern=elevated,
        reason=reason,
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

    pool = priority + rest
    random.shuffle(priority)
    for factor in priority[: max(0, n - len(suggestions))]:
        suggestions.append(f"{factor['name']}: {factor['suggestion']}")

    # Top up from rest if needed
    for factor in rest:
        if len(suggestions) >= n + (1 if elevated_concern else 0):
            break
        suggestions.append(f"{factor['name']}: {factor['suggestion']}")

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
        "peer_expected_prevalence_pct": round(bench.combined_expected_prevalence * 100, 2),
        "scd_peer_prevalence_pct": round(bench.scd_peer_prevalence * 100, 2),
        "elevated_concern": traj.elevated_concern,
        "concern_reason": traj.reason,
        "suggestions": suggestions,
        "citations": bench.citations,
        "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
    }
