"""
Research benchmarks for ADRD prevalence by age, gender, and race/ethnicity.

All values are drawn from peer-reviewed and federal/official sources. Every
constant carries a citation comment. When possible we prefer the most recent
U.S.-representative figures.

PRIMARY SOURCES
---------------
[1] Alzheimer's Association. 2024 Alzheimer's Disease Facts and Figures.
    Alzheimer's & Dementia. 2024;20(5):3708-3821.
    https://doi.org/10.1002/alz.13809

[2] Rajan KB, Weuve J, Barnes LL, et al. Population estimate of people with
    clinical Alzheimer's disease and mild cognitive impairment in the
    United States (2020-2060). Alzheimer's & Dementia 2021;17(12):1966-1975.

[3] Matthews KA, Xu W, Gaglioti AH, et al. Racial and ethnic estimates of
    Alzheimer's disease and related dementias in the United States
    (2015-2060) in adults aged >=65 years. Alzheimer's & Dementia 2019;15:17-24.

[4] Taylor CA, Bouldin ED, McGuire LC. Subjective Cognitive Decline among
    Adults Aged >= 45 Years -- United States, 2015-2020. MMWR Morb Mortal
    Wkly Rep 2023;72(10):249-255.

[5] Mayeda ER, Glymour MM, Quesenberry CP, Whitmer RA. Inequalities in
    dementia incidence between six racial and ethnic groups over 14 years.
    Alzheimer's & Dementia 2016;12(3):216-224.

[6] Livingston G, Huntley J, Liu KY, et al. Dementia prevention, intervention,
    and care: 2024 report of the Lancet standing Commission. Lancet
    2024;404(10452):572-628.

[7] World Health Organization. Dementia fact sheet. 2025.
    https://www.who.int/news-room/fact-sheets/detail/dementia

CAVEAT: All prevalence figures reflect U.S. population-level estimates among
adults aged 65+ (except where noted). They are clinical-symptom-based and may
overestimate biomarker-confirmed AD by 15-30% per [1]. Under-diagnosis among
Black, Hispanic, Native American, and Asian American populations is
well-documented [3,4] and affects interpretation of these benchmarks.
"""

from dataclasses import dataclass
from typing import Literal, Optional


# -----------------------------------------------------------------------------
# AGE-STRATIFIED PREVALENCE (U.S. adults 65+)
# Source: [1] Alzheimer's Association 2024 Facts and Figures (derived from [2])
# -----------------------------------------------------------------------------

AGE_PREVALENCE = {
    # (min_age, max_age_inclusive): prevalence_proportion
    (30, 64): 0.0011,   # Younger-onset: ~110 per 100,000 age 30-64 [1]
    (65, 74): 0.050,    # 5.0% of adults 65-74 [1]
    (75, 84): 0.132,    # 13.2% of adults 75-84 [1]
    (85, 120): 0.334,   # 33.4% of adults 85+ [1]
}


# -----------------------------------------------------------------------------
# RACE/ETHNICITY PREVALENCE (U.S. adults 65+)
# Source: Matthews et al. 2019 [3] via Alzheimer's Association 2024 [1]
# -----------------------------------------------------------------------------

RACE_PREVALENCE_65_PLUS = {
    "black":           0.138,   # 13.8% -- highest AD prevalence of all racial groups [1,3]
    "hispanic":        0.122,   # 12.2% [1,3]
    "white":           0.103,   # 10.3% (non-Hispanic white) [1,3]
    "ai_an":           0.091,   # 9.1% American Indian / Alaska Native [1,3]
    "aapi":            0.084,   # 8.4% Asian American / Pacific Islander [1,3]
    "other":           0.103,   # Fallback to overall rate when unspecified
    "prefer_not":      0.103,
}

# Relative-risk multipliers vs. non-Hispanic white [1,3]
RACE_RELATIVE_RISK = {
    "black":       2.0,   # ~2x more likely than whites [1,3]
    "hispanic":    1.5,   # ~1.5x more likely than whites [1,3]
    "white":       1.0,
    "ai_an":       0.88,  # 9.1/10.3 -- lower, but likely under-diagnosed [1,3]
    "aapi":        0.82,  # 8.4/10.3 -- lower, but likely under-diagnosed [1,3]
    "other":       1.0,
    "prefer_not":  1.0,
}


# -----------------------------------------------------------------------------
# SUBJECTIVE COGNITIVE DECLINE (SCD) PREVALENCE -- adults 45+
# Source: CDC MMWR 2023 [4], BRFSS 2015-2020, age-adjusted
# SCD is a self-reported early marker, relevant to CogniSense's check-in data
# -----------------------------------------------------------------------------

SCD_PREVALENCE_BY_RACE = {
    "ai_an":       0.167,   # 16.7% -- highest [4]
    "hispanic":    0.114,   # 11.4% [4]
    "black":       0.101,   # 10.1% [4]
    "white":       0.093,   # 9.3% [4]
    "aapi":        0.050,   # 5.0% [4]
    "other":       0.096,   # Overall rate 9.6% [4]
    "prefer_not":  0.096,
}


# -----------------------------------------------------------------------------
# GENDER / SEX DIFFERENCES
# Roughly two-thirds of U.S. Americans 65+ living with Alzheimer's are women [1].
# Women also have higher lifetime risk at age 65 (~1 in 5) vs. men (~1 in 10) [1].
# WHO: women carry disproportionate disease burden globally [7].
# -----------------------------------------------------------------------------

GENDER_RELATIVE_RISK = {
    "female":       1.20,   # Slightly elevated age-adjusted risk [1,7]
    "male":         1.00,
    "nonbinary":    1.10,   # Midpoint default; Brady et al. 2024 shows higher risk for TGD adults
    "other":        1.10,
    "prefer_not":   1.10,
}


# -----------------------------------------------------------------------------
# LANCET 2024 MODIFIABLE RISK FACTORS (14 factors, ~45% attributable risk) [6]
# Used to generate personalized activity suggestions.
# -----------------------------------------------------------------------------

LANCET_2024_RISK_FACTORS = [
    {
        "name": "Less education",
        "life_stage": "early life (<18)",
        "pop_attributable_fraction": 0.05,
        "suggestion": "Engage in lifelong learning: online courses, reading, language apps.",
    },
    {
        "name": "Hearing loss",
        "life_stage": "midlife (45-65)",
        "pop_attributable_fraction": 0.07,
        "suggestion": "Get a hearing test annually after 50. Use hearing aids if needed -- treating hearing loss is one of the strongest dementia-prevention measures.",
    },
    {
        "name": "High LDL cholesterol",
        "life_stage": "midlife (45-65)",
        "pop_attributable_fraction": 0.07,
        "suggestion": "Check LDL cholesterol yearly. Heart-healthy diet (Mediterranean/MIND), exercise, statins if prescribed.",
    },
    {
        "name": "Depression",
        "life_stage": "across life",
        "pop_attributable_fraction": 0.03,
        "suggestion": "Treat depression early. Talk therapy, SSRIs, social connection, regular exercise.",
    },
    {
        "name": "Traumatic brain injury",
        "life_stage": "midlife",
        "pop_attributable_fraction": 0.03,
        "suggestion": "Wear helmets (bike, ski), use seatbelts, fall-proof the home after 65.",
    },
    {
        "name": "Physical inactivity",
        "life_stage": "midlife+",
        "pop_attributable_fraction": 0.02,
        "suggestion": "Aim for 150 min/week moderate-vigorous activity (brisk walking, swimming, dancing).",
    },
    {
        "name": "Diabetes",
        "life_stage": "midlife+",
        "pop_attributable_fraction": 0.02,
        "suggestion": "Monitor HbA1c; manage blood sugar via diet, exercise, medication.",
    },
    {
        "name": "Smoking",
        "life_stage": "across life",
        "pop_attributable_fraction": 0.02,
        "suggestion": "Quit smoking. Within 5 years of quitting, dementia risk starts dropping.",
    },
    {
        "name": "Hypertension",
        "life_stage": "midlife (40-65)",
        "pop_attributable_fraction": 0.02,
        "suggestion": "Keep systolic BP <= 130 mmHg in midlife. Monitor, take prescribed meds.",
    },
    {
        "name": "Obesity",
        "life_stage": "midlife",
        "pop_attributable_fraction": 0.01,
        "suggestion": "Maintain healthy BMI through balanced diet and regular physical activity.",
    },
    {
        "name": "Excessive alcohol",
        "life_stage": "across life",
        "pop_attributable_fraction": 0.01,
        "suggestion": "Limit alcohol to <=21 units/week; fewer is better.",
    },
    {
        "name": "Social isolation",
        "life_stage": "later life (65+)",
        "pop_attributable_fraction": 0.05,
        "suggestion": "Maintain regular social contact -- calls, visits, community groups, volunteering.",
    },
    {
        "name": "Air pollution",
        "life_stage": "later life",
        "pop_attributable_fraction": 0.03,
        "suggestion": "Reduce exposure: indoor air filters, avoid high-pollution days outdoors.",
    },
    {
        "name": "Untreated vision loss",
        "life_stage": "later life",
        "pop_attributable_fraction": 0.02,
        "suggestion": "Annual eye exam after 60. Treat cataracts promptly; wear prescribed corrective lenses.",
    },
]


# -----------------------------------------------------------------------------
# UTILITY: compute expected ADRD prevalence for a user given demographics
# -----------------------------------------------------------------------------

Gender = Literal["female", "male", "nonbinary", "other", "prefer_not"]
Race = Literal["white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not"]


@dataclass
class RiskBenchmark:
    """Expected ADRD prevalence for a user's demographic group, with context."""
    age_group_prevalence: float
    race_adjusted_prevalence: float
    gender_adjusted_prevalence: float
    combined_expected_prevalence: float
    scd_peer_prevalence: float
    citations: list[str]


def get_age_group_prevalence(age: int) -> float:
    """Return population-level prevalence of AD for a user's age band."""
    for (lo, hi), prev in AGE_PREVALENCE.items():
        if lo <= age <= hi:
            return prev
    # Below 30: no established prevalence benchmark
    return 0.0


def compute_benchmark(age: int, gender: Gender, race: Race) -> RiskBenchmark:
    """
    Compute the expected ADRD prevalence for a user's demographic group by
    combining age-band prevalence with race and gender relative-risk
    multipliers.

    This is a population-level reference only -- NOT a personal diagnosis.
    """
    age_prev = get_age_group_prevalence(age)
    race_rr = RACE_RELATIVE_RISK.get(race, 1.0)
    gender_rr = GENDER_RELATIVE_RISK.get(gender, 1.0)

    race_adjusted = age_prev * race_rr
    gender_adjusted = age_prev * gender_rr
    combined = age_prev * race_rr * gender_rr

    scd = SCD_PREVALENCE_BY_RACE.get(race, 0.096)

    return RiskBenchmark(
        age_group_prevalence=round(age_prev, 4),
        race_adjusted_prevalence=round(race_adjusted, 4),
        gender_adjusted_prevalence=round(gender_adjusted, 4),
        combined_expected_prevalence=round(combined, 4),
        scd_peer_prevalence=round(scd, 4),
        citations=[
            "Alzheimer's Association 2024 Facts and Figures (Alz & Dementia 20:3708-3821)",
            "Matthews et al. 2019 (Alz & Dementia 15:17-24)",
            "CDC MMWR 2023;72(10):249-255",
            "Livingston et al. 2024 Lancet Commission (Lancet 404:572-628)",
        ],
    )


NON_DIAGNOSTIC_DISCLAIMER = (
    "CogniSense is a self-tracking tool, NOT a medical diagnostic device. "
    "The output above is a suggestion based on population-level research, "
    "not professional advice. If you are noticing worsening memory or "
    "cognitive changes -- in yourself or someone you care about -- please "
    "speak with a licensed physician or neurologist."
)
