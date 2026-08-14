# CogniSense model validation report

HEADLINE: behavioral feature set AUC = {candidate_auc} under user-level nested CV  |  controls: {trust_verdict}

Run ID: {run_id}   Date: {date}   Git commit: {git_commit}   Config hash: {config_hash}
Seed: {seed}   Key lib versions: {key_lib_versions}
Platform: {platform}
Cohort: {cohort_name}   Users: {n_users}   Rows: {n_rows}   Features: {n_features}

## 1. Clinical validity

{clinical_validity_note}

This report measures whether a feature set separates two classes under honest
validation. It does not measure whether those classes correspond to anything
in a real person's brain. Do not quote the headline number as evidence that
CogniSense detects cognitive decline.

## 2. Accuracy

Validation: nested cross-validation, {outer_folds} outer folds, split on user_id
so that no person appears on both sides of a fold.

| Model                        | Metric | Value [95% CI]      |
|------------------------------|--------|---------------------|
| Behavioral features (8)      | AUC    | {candidate_auc}     |
| Behavioral features (8)      | Brier  | {candidate_brier}   |
| Age-only baseline            | AUC    | {baseline_auc}      |

Brier is a calibration measure: lower is better, and it asks whether a score of
0.7 actually means a 70% chance. A model can discriminate well (high AUC) and
still be badly calibrated, which matters here because the number is shown to a
person as if it means something on its own.

## 3. Negative controls

- **Permuted labels** (expect chance): {perm_auc}
  {perm_interpretation}

- **Versus baseline** (expect the candidate to win): {baseline_delta}
  {baseline_interpretation}

- **Age regressed out** (expect signal to survive): {confound_auc}
  {confound_interpretation}

The confound regression is fitted inside each training fold and applied to the
held-out fold using the training-fold coefficients, so this control does not
leak. The permutation shuffles labels between users rather than between rows,
which keeps each person's days on a single label and puts the null where it
belongs.

## 4. Verdict

{trust_verdict}

A failed control invalidates the headline. Fix the pipeline before reporting
anything above.
