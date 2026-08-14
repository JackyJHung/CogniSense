"""Validation harness for the behavioral biomarker feature set.

This is the piece the app never had. `train_models.py` fits a CNN and an MLP on
synthetic data, prints the TRAINING accuracy, saves a checkpoint, and that is
the last time anyone asks whether the models work. Training accuracy on data
you generated is not a result.

WHAT THIS CAN AND CANNOT TELL YOU
---------------------------------
CogniSense has no ground-truth labels. Nobody in cognisense.db carries a
clinical diagnosis. So this harness answers a narrow question honestly instead
of a broad question dishonestly.

  Answered      Under user-level nested CV, does the 8-feature behavioral
                vector separate the two classes better than chance, and better
                than knowing the person's demographics alone? Does that hold
                once age is regressed out?

  NOT answered  Does a low CogniSense score correspond to MCI or Alzheimer's in
                a real person? That requires a labelled clinical corpus
                (DementiaBank Pitt, ADReSS, ADNI) under ethics approval, and it
                is the single largest gap between this repository and any
                defensible product claim. Nothing here closes it.

Swapping `synthetic_cohort()` for a loader over labelled real data is the only
change needed once such data exists; everything downstream is domain-agnostic.

WHY THE COHORT IS GROUPED
-------------------------
Each simulated user contributes MANY daily rows sharing one label -- the real
shape of the app's data. Splitting those rows at random would put Tuesday in
train and Wednesday in test for the same person, and the model would be scored
on recognising a familiar individual rather than on detecting cognitive change.
`core.splits` splits on user_id, so that cannot happen; the permuted-label
control below is what proves it did not.

Run:
    cd backend
    python -m app.ml.validate
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from core.controls import (
    baseline_comparison,
    confound_control,
    overall_verdict,
    permuted_label_control,
)
from core.env import capture_env, hash_config
from core.evaluate import EvalResult, evaluate_binary
from core.pipelines import build_classifier_pipeline
from core.report import make_run_id, now_iso, render_report
from core.seeding import DEFAULT_SEED, set_global_seed

# Mirrors the layout built by app.ml.behavioral_model.build_behavioral_feature_vector.
# Declared locally rather than imported so this harness stays runnable without
# torch installed -- it evaluates the FEATURE SET, not the torch checkpoint.
FEATURE_NAMES = [
    "activity_recall_accuracy",
    "association_accuracy",
    "avg_response_latency_z",
    "linguistic_richness",
    "word_count_norm",
    "latency_variance",
    "checkin_consistency",
    "speech_biomarker_score",
]

TEMPLATE = Path(__file__).resolve().parents[1] / "reports" / "validation_report.md"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "results"


@dataclass
class Cohort:
    """One row per (user, day). `y` and `age` are constant within a user."""

    X: np.ndarray            # (n_rows, 8) behavioral features
    y: np.ndarray            # (n_rows,) 0 = typical, 1 = concerning
    user_ids: np.ndarray     # (n_rows,) grouping key for CV
    age: np.ndarray          # (n_rows,) years
    demographics: np.ndarray  # (n_rows, 1) age only, for the baseline model

    @property
    def n_users(self) -> int:
        return len(set(self.user_ids.tolist()))


def synthetic_cohort(
    n_users: int = 140,
    min_days: int = 10,
    max_days: int = 40,
    seed: int = DEFAULT_SEED,
) -> Cohort:
    """Simulate a grouped cohort with a deliberately confounded age effect.

    Age raises the probability of the 'concerning' label, exactly as ADRD
    prevalence does in the real benchmarks. That makes the two controls below
    genuinely informative rather than decorative:

      - a demographics-only baseline is BETTER than chance, so beating it is a
        real bar rather than a formality
      - regressing age out is a real test of whether the behavioral features
        carry anything beyond "this person is old"
    """
    rng = np.random.default_rng(seed)
    rows, ys, ids, ages = [], [], [], []

    for u in range(n_users):
        age = int(np.clip(rng.normal(68, 11), 40, 95))
        # Age-driven prevalence, loosely tracking AGE_PREVALENCE in
        # research_benchmarks. Bounded so neither class collapses.
        p_concern = float(np.clip((age - 55) / 60.0, 0.05, 0.75))
        label = int(rng.random() < p_concern)

        # Per-user offset: people differ from each other far more than they
        # differ from themselves day to day. This is what makes leakage both
        # tempting and destructive -- a model can identify the PERSON from a
        # single day's features, so any split that lets one person span the
        # fold boundary scores recognition instead of detection.
        user_offset = rng.normal(0, 0.15, size=len(FEATURE_NAMES))
        n_days = int(rng.integers(min_days, max_days + 1))

        # The class distributions overlap heavily and on purpose. Early
        # cognitive change is a subtle shift against large individual variation,
        # not two clean clusters; a simulation with cleanly separated classes
        # yields AUC 1.0 and teaches nothing about the machinery under test.
        for _ in range(n_days):
            if label == 0:
                base = np.array([
                    rng.normal(0.72, 0.16),   # activity recall
                    rng.normal(0.74, 0.16),   # association accuracy
                    rng.normal(0.10, 0.55),   # latency z
                    rng.normal(0.55, 0.14),   # lexical diversity
                    rng.normal(0.95, 0.25),   # word count norm
                    abs(rng.normal(0.14, 0.08)),
                    rng.normal(0.85, 0.13),   # checkin consistency
                    rng.normal(0.72, 0.14),   # speech score
                ])
            else:
                base = np.array([
                    rng.normal(0.56, 0.18),
                    rng.normal(0.58, 0.19),
                    rng.normal(0.85, 0.70),
                    rng.normal(0.44, 0.14),
                    rng.normal(0.70, 0.25),
                    abs(rng.normal(0.26, 0.11)),
                    rng.normal(0.75, 0.16),
                    rng.normal(0.58, 0.17),
                ])
            row = base + user_offset
            # Keep bounded features in range; latency z is unbounded by design.
            row[[0, 1, 3, 6, 7]] = np.clip(row[[0, 1, 3, 6, 7]], 0.0, 1.0)
            row[4] = np.clip(row[4], 0.0, 2.0)
            row[5] = np.clip(row[5], 0.0, 1.0)

            rows.append(row)
            ys.append(label)
            ids.append(f"U-{u:04d}")
            ages.append(age)

    X = np.vstack(rows)
    age_arr = np.asarray(ages, dtype=float)
    return Cohort(
        X=X,
        y=np.asarray(ys, dtype=int),
        user_ids=np.asarray(ids),
        age=age_arr,
        demographics=age_arr.reshape(-1, 1),
    )


def _evaluator(outer_folds: int, seed: int):
    """Bind an evaluator with fixed settings, for the control functions."""

    def run(X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> EvalResult:
        return evaluate_binary(
            X, y, groups,
            pipeline_factory=lambda: build_classifier_pipeline(random_state=seed),
            target="behavioral_features",
            outer_folds=outer_folds,
            random_state=seed,
        )

    return run


def _confounded_evaluator(outer_folds: int, seed: int):
    def run(
        X: np.ndarray, y: np.ndarray, groups: np.ndarray, confounds: np.ndarray
    ) -> EvalResult:
        return evaluate_binary(
            X, y, groups,
            pipeline_factory=lambda: build_classifier_pipeline(random_state=seed),
            target="behavioral_features_age_regressed",
            confounds=confounds,
            outer_folds=outer_folds,
            random_state=seed,
        )

    return run


def run_validation(
    cohort: Cohort | None = None,
    outer_folds: int = 5,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Evaluate the feature set, run all three controls, return report fields."""
    set_global_seed(seed)
    cohort = cohort or synthetic_cohort(seed=seed)

    evaluator = _evaluator(outer_folds, seed)

    # 1. The candidate: behavioral features.
    candidate = evaluator(cohort.X, cohort.y, cohort.user_ids)

    # 2. Baseline: age alone. Evaluated on identical rows so the comparison
    #    can be paired.
    baseline = evaluate_binary(
        cohort.demographics, cohort.y, cohort.user_ids,
        pipeline_factory=lambda: build_classifier_pipeline(random_state=seed),
        target="age_only_baseline",
        outer_folds=outer_folds,
        random_state=seed,
    )

    # 3. Controls.
    perm = permuted_label_control(
        cohort.X, cohort.y, cohort.user_ids, evaluator, random_state=seed,
    )
    versus_baseline = baseline_comparison(
        candidate, baseline, baseline_name="age-only baseline",
        metric_fn=roc_auc_score, random_state=seed,
    )
    confound = confound_control(
        cohort.X, cohort.y, cohort.user_ids, cohort.demographics,
        _confounded_evaluator(outer_folds, seed),
        original=candidate,
        confound_names="age",
    )

    controls = [perm, versus_baseline, confound]
    env = capture_env()
    config = {
        "outer_folds": outer_folds,
        "seed": seed,
        "n_users": cohort.n_users,
        "features": FEATURE_NAMES,
    }

    return {
        "run_id": make_run_id("validate"),
        "date": now_iso(),
        "git_commit": env.git_commit or "n/a (not a git repo)",
        "config_hash": hash_config(config),
        "seed": seed,
        "key_lib_versions": env.summary(),
        "platform": env.platform,
        "cohort_name": "synthetic grouped cohort (NOT clinical data)",
        "n_users": cohort.n_users,
        "n_rows": int(cohort.X.shape[0]),
        "n_features": len(FEATURE_NAMES),
        "outer_folds": candidate.outer_folds,
        "candidate_auc": candidate.metric,
        "candidate_brier": candidate.calibration,
        "baseline_auc": baseline.metric,
        "perm_auc": perm.metric,
        "perm_interpretation": perm.interpretation,
        "baseline_delta": versus_baseline.metric,
        "baseline_interpretation": versus_baseline.interpretation,
        "confound_auc": confound.metric,
        "confound_interpretation": confound.interpretation,
        "trust_verdict": overall_verdict(controls),
        "clinical_validity_note": (
            "NOT ESTABLISHED. This run used simulated data with simulated "
            "labels. No claim about real cognitive decline follows from it."
        ),
    }


def main() -> None:
    fields = run_validation()
    md_path, json_path = render_report(
        TEMPLATE, fields, DEFAULT_OUT_DIR,
        run_id=str(fields["run_id"]), filename_stem="validation",
    )
    print(f"\nAUC        {fields['candidate_auc'].render()}")
    print(f"baseline   {fields['baseline_auc'].render()}")
    print(f"permuted   {fields['perm_auc'].render()}")
    print(f"verdict    {fields['trust_verdict']}")
    print(f"\nreport -> {md_path}")
    print(f"json   -> {json_path}")


if __name__ == "__main__":
    main()
