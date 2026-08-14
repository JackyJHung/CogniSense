"""Per-record QC gates: pass, flag, or exclude.

The pass/flag/exclude shape is ported from the research pipeline's `qc/gates.py`.
The gates themselves are new -- the originals checked registration NMI and
streamline counts, which have no meaning here. These check the things that
actually invalidate a CogniSense record.

A gate returning `exclude` keeps the record out of any model fit or trend
report. `flag` keeps it but counts it in the report's flagged line, so a run
built mostly on shaky records cannot look clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["pass", "flag", "exclude"]

# Two weeks of daily check-ins before a trajectory claim is allowed. Matches
# MINIMUM_CHECKINS_FOR_WARNING in the risk layer; both exist because a "decline"
# measured over four days is mostly measurement noise.
MIN_CHECKINS_FOR_TRAJECTORY = 14
MIN_CHECKINS_FOR_BASELINE = 7


@dataclass
class GateResult:
    verdict: Verdict
    reason: str

    @property
    def passed(self) -> bool:
        return self.verdict != "exclude"

    @property
    def flagged(self) -> bool:
        return self.verdict == "flag"


def checkin_volume_gate(
    n_checkins: int,
    min_for_trajectory: int = MIN_CHECKINS_FOR_TRAJECTORY,
    min_for_baseline: int = MIN_CHECKINS_FOR_BASELINE,
) -> GateResult:
    """Enough history to say anything about a trend?"""
    if n_checkins < min_for_baseline:
        return GateResult(
            "exclude",
            f"{n_checkins} check-ins < {min_for_baseline} needed to establish a baseline",
        )
    if n_checkins < min_for_trajectory:
        return GateResult(
            "flag",
            f"{n_checkins} check-ins < {min_for_trajectory} needed for a trajectory claim",
        )
    return GateResult("pass", "")


def completeness_gate(
    n_expected_fields: int, n_present_fields: int, min_fraction: float = 0.6,
) -> GateResult:
    """Partially-filled evening check-ins produce misleading composite scores."""
    if n_expected_fields <= 0:
        return GateResult("exclude", "no expected fields declared")
    frac = n_present_fields / n_expected_fields
    if frac < min_fraction:
        return GateResult(
            "exclude", f"only {frac:.0%} of scoring inputs present (min {min_fraction:.0%})"
        )
    if frac < 1.0:
        return GateResult("flag", f"{frac:.0%} of scoring inputs present")
    return GateResult("pass", "")


def audio_quality_gate(
    duration_s: float | None,
    min_duration_s: float = 3.0,
    max_duration_s: float = 120.0,
) -> GateResult:
    """The speech model expects ~5 s of speech; clips outside that are noise.

    Audio is optional in the check-in flow, so a missing clip is a flag rather
    than an exclusion -- the behavioral model still scores without it.
    """
    if duration_s is None:
        return GateResult("flag", "no audio submitted; speech biomarker unavailable")
    if duration_s < min_duration_s:
        return GateResult(
            "exclude", f"audio {duration_s:.1f}s shorter than {min_duration_s}s minimum"
        )
    if duration_s > max_duration_s:
        return GateResult("flag", f"audio {duration_s:.1f}s longer than expected")
    return GateResult("pass", "")


def latency_plausibility_gate(
    avg_latency_ms: int | None,
    floor_ms: int = 250,
    ceiling_ms: int = 120_000,
) -> GateResult:
    """Guard against a distracted or automated session.

    Below the floor the person cannot have read the cue; above the ceiling they
    walked away mid-test. Either way the latency feature is not measuring recall
    speed, and latency feeds the behavioral model directly.
    """
    if avg_latency_ms is None:
        return GateResult("flag", "no latency recorded")
    if avg_latency_ms < floor_ms:
        return GateResult(
            "exclude", f"mean latency {avg_latency_ms}ms below plausible floor {floor_ms}ms"
        )
    if avg_latency_ms > ceiling_ms:
        return GateResult(
            "exclude", f"mean latency {avg_latency_ms}ms above ceiling {ceiling_ms}ms"
        )
    return GateResult("pass", "")


def combine(*gates: GateResult) -> GateResult:
    """Worst verdict wins; reasons are concatenated."""
    reasons = [g.reason for g in gates if g.reason]
    joined = "; ".join(reasons)
    if any(g.verdict == "exclude" for g in gates):
        return GateResult("exclude", joined)
    if any(g.verdict == "flag" for g in gates):
        return GateResult("flag", joined)
    return GateResult("pass", joined)
