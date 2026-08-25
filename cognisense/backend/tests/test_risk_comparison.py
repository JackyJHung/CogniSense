"""Unit tests for app/ml/risk_comparison.py."""

import random

import pytest

from app.data.research_benchmarks import LANCET_2024_RISK_FACTORS, NON_DIAGNOSTIC_DISCLAIMER
from app.ml.risk_comparison import (
    MINIMUM_CHECKINS_FOR_WARNING,
    WARNING_ABSOLUTE_FLOOR,
    analyze_trajectory,
    build_risk_comparison,
    personalized_suggestions,
)


# ---------- analyze_trajectory ----------

def test_trajectory_averages_and_pct_change():
    traj = analyze_trajectory([0.8, 0.6], [0.9, 0.7], total_checkins=4)
    assert traj.current_avg == 0.7
    assert traj.baseline_avg == 0.8
    assert traj.pct_change == pytest.approx(-0.125, abs=1e-3)


def test_trajectory_with_no_scores_is_zeroed():
    traj = analyze_trajectory([], [], total_checkins=0)
    assert (traj.current_avg, traj.baseline_avg, traj.pct_change) == (0.0, 0.0, 0.0)
    assert traj.elevated_concern is False
    assert traj.reason is None


def test_trajectory_without_baseline_uses_current_average():
    traj = analyze_trajectory([0.5, 0.7], [], total_checkins=2)
    assert traj.baseline_avg == 0.6
    assert traj.pct_change == 0.0


def test_no_warning_before_minimum_checkins_even_on_a_steep_drop():
    traj = analyze_trajectory([0.2], [0.9], total_checkins=MINIMUM_CHECKINS_FOR_WARNING - 1)
    assert traj.pct_change < -0.20
    assert traj.elevated_concern is False
    assert traj.reason is None


def test_warning_on_sustained_drop_versus_own_baseline():
    traj = analyze_trajectory([0.60], [0.90], total_checkins=MINIMUM_CHECKINS_FOR_WARNING)
    assert traj.elevated_concern is True
    assert "dropped" in traj.reason
    assert "33%" in traj.reason


def test_warning_on_absolute_floor_without_a_drop():
    # Stable trajectory (no meaningful drop) but scores below the absolute floor
    traj = analyze_trajectory([0.30], [0.31], total_checkins=20)
    assert traj.current_avg < WARNING_ABSOLUTE_FLOOR
    assert traj.elevated_concern is True
    assert "consistently low" in traj.reason


def test_drop_reason_takes_precedence_over_absolute_floor():
    traj = analyze_trajectory([0.20], [0.90], total_checkins=20)
    assert traj.elevated_concern is True
    assert "dropped" in traj.reason


def test_improving_trajectory_does_not_warn():
    traj = analyze_trajectory([0.9], [0.6], total_checkins=30)
    assert traj.pct_change > 0
    assert traj.elevated_concern is False


def test_trajectory_tolerates_zero_baseline():
    traj = analyze_trajectory([0.5], [0.0], total_checkins=30)
    assert traj.pct_change == 0.0
    assert traj.elevated_concern is False


# ---------- personalized_suggestions ----------

@pytest.mark.parametrize("age, stage", [(30, "early life"), (55, "midlife"), (80, "later life")])
def test_suggestions_are_biased_to_the_users_life_stage(age, stage):
    random.seed(0)
    suggestions = personalized_suggestions(age, elevated_concern=False, n=4)
    stage_names = {
        f["name"] for f in LANCET_2024_RISK_FACTORS if stage in f["life_stage"]
    }
    assert any(s.split(":")[0] in stage_names for s in suggestions)


def test_suggestions_returns_requested_count():
    random.seed(1)
    assert len(personalized_suggestions(70, elevated_concern=False, n=3)) == 3
    assert len(personalized_suggestions(70, elevated_concern=False, n=1)) == 1


def test_elevated_concern_prepends_see_a_doctor_and_adds_one_suggestion():
    random.seed(2)
    suggestions = personalized_suggestions(70, elevated_concern=True, n=4)
    assert len(suggestions) == 5
    assert "primary care doctor" in suggestions[0]


def test_suggestions_are_unique_and_formatted_as_name_colon_advice():
    random.seed(3)
    suggestions = personalized_suggestions(50, elevated_concern=False, n=6)
    assert len(set(suggestions)) == len(suggestions)
    names = {f["name"] for f in LANCET_2024_RISK_FACTORS}
    for s in suggestions:
        assert s.split(":")[0] in names


def test_suggestions_top_up_from_other_life_stages_when_n_exceeds_priority_pool():
    random.seed(4)
    # Only 2 early-life/across-life factors exist for under-45s; asking for 8
    # forces the top-up branch that pulls from the remaining factors.
    suggestions = personalized_suggestions(30, elevated_concern=False, n=8)
    assert len(suggestions) == 8
    assert len(set(suggestions)) == 8


# ---------- build_risk_comparison ----------

def test_build_risk_comparison_payload_shape():
    random.seed(5)
    payload = build_risk_comparison(
        age=70,
        gender="female",
        race="black",
        recent_scores=[0.8, 0.82],
        baseline_scores=[0.79],
        total_checkins=20,
    )

    assert payload["user_recent_avg_score"] == pytest.approx(0.81, abs=1e-3)
    # 5.0% age prevalence * 2.0 (black) * 1.2 (female) = 12.0%
    assert payload["peer_expected_prevalence_pct"] == pytest.approx(12.0, abs=0.05)
    assert payload["scd_peer_prevalence_pct"] == pytest.approx(10.1, abs=0.05)
    assert payload["elevated_concern"] is False
    assert payload["concern_reason"] is None
    assert len(payload["suggestions"]) == 4
    assert payload["citations"]
    assert payload["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER


def test_build_risk_comparison_flags_concern_and_includes_doctor_suggestion():
    random.seed(6)
    payload = build_risk_comparison(
        age=80,
        gender="male",
        race="white",
        recent_scores=[0.4],
        baseline_scores=[0.85],
        total_checkins=30,
    )
    assert payload["elevated_concern"] is True
    assert "dropped" in payload["concern_reason"]
    assert "primary care doctor" in payload["suggestions"][0]


def test_build_risk_comparison_percentages_are_rounded_to_two_places():
    random.seed(7)
    payload = build_risk_comparison(
        age=85,
        gender="nonbinary",
        race="hispanic",
        recent_scores=[0.5],
        baseline_scores=[0.5],
        total_checkins=1,
    )
    assert payload["peer_expected_prevalence_pct"] == round(payload["peer_expected_prevalence_pct"], 2)
    assert payload["scd_peer_prevalence_pct"] == round(payload["scd_peer_prevalence_pct"], 2)
