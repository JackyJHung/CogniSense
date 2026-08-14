"""Shared methodology layer for CogniSense.

This package is the part of the glioma dMRI research pipeline that was worth
keeping: the machinery for producing a number you can defend. It carries no
domain assumptions -- no MRI, no speech, no check-ins -- so the backend, the
training scripts and any future analysis all measure things the same way.

  stats      MetricCI + bootstrap intervals. Nothing user-facing without one.
  splits     Group-level nested CV. In this app the group is a USER, not a row.
  pipelines  sklearn pipelines that keep preprocessing inside the training fold.
  evaluate   Nested-CV evaluation -> out-of-fold predictions + CI-bearing metrics.
  controls   Permuted-label, baseline and confound checks. The trust audit.
  qc         pass / flag / exclude gates for individual records.
  seeding    One seed for random, numpy and torch.
  env        Environment capture for the report header.
  report     Contract-enforcing Markdown + JSON renderer.

Origin: C:\\Users\\jjhun\\projects\\cognisense (UCSF-PDGM glioma pipeline). The
tumour-specific stages -- DWI loading, lesion-aware registration, CSD,
tractography, connectome construction -- were deliberately left behind; they
are glioma-specific and were never implemented.
"""

from core.stats import (
    NA,
    MetricCI,
    bootstrap_ci,
    bootstrap_delta_ci,
    bootstrap_stat_ci,
    paired_bootstrap_delta,
)
from core.splits import OuterFold, assert_no_leakage, grouped_nested_splits
from core.pipelines import build_classifier_pipeline, build_regressor_pipeline
from core.evaluate import EvalResult, evaluate_binary, evaluate_multiclass
from core.controls import (
    ControlResult,
    baseline_comparison,
    confound_control,
    overall_verdict,
    permuted_label_control,
)
from core.qc import GateResult, combine
from core.seeding import DEFAULT_SEED, set_global_seed
from core.env import RunEnv, capture_env, hash_config
from core.report import make_run_id, now_iso, render_report

__all__ = [
    "NA",
    "MetricCI",
    "bootstrap_ci",
    "bootstrap_delta_ci",
    "bootstrap_stat_ci",
    "paired_bootstrap_delta",
    "OuterFold",
    "assert_no_leakage",
    "grouped_nested_splits",
    "build_classifier_pipeline",
    "build_regressor_pipeline",
    "EvalResult",
    "evaluate_binary",
    "evaluate_multiclass",
    "ControlResult",
    "baseline_comparison",
    "confound_control",
    "overall_verdict",
    "permuted_label_control",
    "GateResult",
    "combine",
    "DEFAULT_SEED",
    "set_global_seed",
    "RunEnv",
    "capture_env",
    "hash_config",
    "make_run_id",
    "now_iso",
    "render_report",
]
