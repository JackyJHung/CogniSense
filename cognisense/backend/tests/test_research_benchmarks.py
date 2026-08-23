"""Unit tests for app/data/research_benchmarks.py."""

import pytest

from app.data import (
    AGE_PREVALENCE,
    GENDER_RELATIVE_RISK,
    LANCET_2024_RISK_FACTORS,
    NON_DIAGNOSTIC_DISCLAIMER,
    RACE_PREVALENCE_65_PLUS,
    RiskBenchmark,
    compute_benchmark,
    get_age_group_prevalence,
)
from app.data.research_benchmarks import (
    RACE_RELATIVE_RISK,
    SCD_PREVALENCE_BY_RACE,
)


@pytest.mark.parametrize(
    "age, expected",
    [
        (30, 0.0011),
        (64, 0.0011),
        (65, 0.050),
        (74, 0.050),
        (75, 0.132),
        (84, 0.132),
        (85, 0.334),
        (120, 0.334),
    ],
)
def test_age_group_prevalence_band_boundaries(age, expected):
    assert get_age_group_prevalence(age) == expected


@pytest.mark.parametrize("age", [0, 18, 29, 121, 500])
def test_age_group_prevalence_outside_bands_is_zero(age):
    assert get_age_group_prevalence(age) == 0.0


def test_age_prevalence_increases_with_age():
    prevalences = [get_age_group_prevalence(a) for a in (64, 70, 80, 90)]
    assert prevalences == sorted(prevalences)


def test_compute_benchmark_multiplies_age_race_and_gender_risk():
    bench = compute_benchmark(70, "female", "black")

    assert isinstance(bench, RiskBenchmark)
    assert bench.age_group_prevalence == 0.050
    assert bench.race_adjusted_prevalence == pytest.approx(0.050 * 2.0, abs=1e-4)
    assert bench.gender_adjusted_prevalence == pytest.approx(0.050 * 1.20, abs=1e-4)
    assert bench.combined_expected_prevalence == pytest.approx(0.050 * 2.0 * 1.20, abs=1e-4)
    assert bench.scd_peer_prevalence == SCD_PREVALENCE_BY_RACE["black"]
    assert len(bench.citations) == 4


def test_compute_benchmark_white_male_is_the_unadjusted_reference():
    bench = compute_benchmark(80, "male", "white")
    assert bench.combined_expected_prevalence == pytest.approx(bench.age_group_prevalence, abs=1e-4)


def test_compute_benchmark_unknown_demographics_fall_back_to_neutral_multipliers():
    bench = compute_benchmark(70, "unknown_gender", "unknown_race")  # type: ignore[arg-type]
    assert bench.combined_expected_prevalence == pytest.approx(0.050, abs=1e-4)
    assert bench.scd_peer_prevalence == pytest.approx(0.096, abs=1e-4)


def test_compute_benchmark_young_user_has_no_benchmark():
    bench = compute_benchmark(25, "female", "black")
    assert bench.age_group_prevalence == 0.0
    assert bench.combined_expected_prevalence == 0.0
    # SCD is reported for adults 45+, so the race lookup is still populated
    assert bench.scd_peer_prevalence > 0


def test_compute_benchmark_values_are_rounded_to_four_places():
    bench = compute_benchmark(85, "nonbinary", "hispanic")
    for value in (
        bench.age_group_prevalence,
        bench.race_adjusted_prevalence,
        bench.gender_adjusted_prevalence,
        bench.combined_expected_prevalence,
        bench.scd_peer_prevalence,
    ):
        assert value == round(value, 4)


def test_benchmark_tables_are_consistent():
    assert set(RACE_PREVALENCE_65_PLUS) == set(RACE_RELATIVE_RISK) == set(SCD_PREVALENCE_BY_RACE)
    assert all(0 < p < 1 for p in RACE_PREVALENCE_65_PLUS.values())
    assert all(0 < p < 1 for p in AGE_PREVALENCE.values())
    assert all(rr >= 1.0 for rr in GENDER_RELATIVE_RISK.values())
    assert RACE_RELATIVE_RISK["white"] == 1.0


def test_lancet_risk_factors_are_well_formed():
    assert len(LANCET_2024_RISK_FACTORS) == 14
    for factor in LANCET_2024_RISK_FACTORS:
        assert {"name", "life_stage", "pop_attributable_fraction", "suggestion"} <= set(factor)
        assert factor["suggestion"].strip()
        assert 0 < factor["pop_attributable_fraction"] < 1
    # ~45% of dementia risk is attributable to these factors (Livingston 2024)
    total = sum(f["pop_attributable_fraction"] for f in LANCET_2024_RISK_FACTORS)
    assert 0.40 <= total <= 0.50


def test_disclaimer_states_non_diagnostic_status():
    assert "NOT a medical diagnostic device" in NON_DIAGNOSTIC_DISCLAIMER
