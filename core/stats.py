"""Point estimates that always travel with their uncertainty.

Ported from the research pipeline's `models/classify.bootstrap_metric` and
`report/render.MetricCI` -- two halves of one idea: a number is not a result
until you know how wide it is.

This matters MORE in a consumer app than it did in the research pipeline. The
app tells a person whether their cognition looks like it is slipping. A bare
0.62 is not evidence. `0.62 [0.41, 0.83]` says the honest thing: we cannot tell
yet. Every user-facing number in CogniSense should come out of this module.

Three entry points, matching the three shapes of question the app asks:

  bootstrap_ci        CI on a metric over (y_true, y_score) pairs.
                      "How well does the behavioral model actually classify?"

  bootstrap_stat_ci   CI on a statistic of a single sample.
                      "What is this user's mean daily score, +/- what?"

  bootstrap_delta_ci  CI on the difference between two samples.
                      "Has the user dropped from their own baseline?"
                      This is the one that gates the attention warning.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

NA = "n/a"

DEFAULT_BOOTSTRAP_N = 2000
DEFAULT_CI = 0.95

# Below this many observations a bootstrap CI is theatre: the resamples just
# permute the same handful of points. We return an inestimable MetricCI instead
# of a confidently wrong interval.
MIN_OBS_FOR_CI = 3


@dataclass
class MetricCI:
    """A value bundled with its interval. Renders as '0.812 [0.75, 0.87]'.

    `value is None` means not computed. A value with no interval renders as
    '0.812 [CI n/a]' -- deliberately ugly, because a bare point estimate
    slipping into a user-facing report is a bug, not a formatting choice.
    """

    value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    name: str = ""
    n: int = 0
    note: str = ""

    def render(self, fmt: str = "{:.3f}") -> str:
        if self.value is None:
            return NA
        if self.ci_low is None or self.ci_high is None:
            return f"{fmt.format(self.value)} [CI {NA}]"
        return (
            f"{fmt.format(self.value)} "
            f"[{fmt.format(self.ci_low)}, {fmt.format(self.ci_high)}]"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n": self.n,
            "note": self.note,
        }

    @property
    def is_estimable(self) -> bool:
        return self.value is not None and self.ci_low is not None

    def excludes(self, x: float) -> bool:
        """True only if the whole interval sits on one side of `x`.

        This is the honest form of "is it different from chance / from zero".
        When the interval is unknown this returns False: absence of evidence
        must never read as a positive finding.
        """
        if not self.is_estimable:
            return False
        return x < self.ci_low or x > self.ci_high  # type: ignore[operator]

    def contains(self, x: float) -> bool:
        """True if `x` is inside the interval (i.e. indistinguishable from x)."""
        if not self.is_estimable:
            return False
        return self.ci_low <= x <= self.ci_high  # type: ignore[operator]


def _percentile_ci(samples: np.ndarray, ci: float) -> tuple[float, float] | tuple[None, None]:
    if np.all(np.isnan(samples)):
        return None, None
    alpha = (1.0 - ci) / 2.0
    lo, hi = np.nanpercentile(samples, [100.0 * alpha, 100.0 * (1.0 - alpha)])
    return float(lo), float(hi)


def bootstrap_ci(
    y_true: np.ndarray,
    y_score: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    name: str = "",
    n: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_CI,
    random_state: int = 42,
) -> MetricCI:
    """Resample held-out predictions with replacement; percentile interval.

    Resamples PAIRS, so the (y_true, y_score) correspondence is preserved.
    Metric functions that raise on degenerate resamples (e.g. roc_auc_score on
    a resample that drew a single class) contribute NaN and are excluded from
    the percentiles rather than aborting the run.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    n_obs = y_true.shape[0]

    if n_obs < MIN_OBS_FOR_CI:
        return MetricCI(name=name, n=n_obs, note=f"n={n_obs} below minimum for a CI")

    try:
        point = float(metric_fn(y_true, y_score))
    except ValueError as exc:
        return MetricCI(name=name, n=n_obs, note=f"metric undefined: {exc}")

    rng = np.random.default_rng(random_state)
    samples = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, n_obs, n_obs)
        try:
            samples[i] = metric_fn(y_true[idx], y_score[idx])
        except ValueError:
            samples[i] = np.nan

    lo, hi = _percentile_ci(samples, ci)
    return MetricCI(value=point, ci_low=lo, ci_high=hi, name=name, n=n_obs)


def paired_bootstrap_delta(
    y_true: np.ndarray,
    score_a: np.ndarray,
    score_b: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    name: str = "",
    n: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_CI,
    random_state: int = 42,
) -> MetricCI:
    """CI on metric(a) - metric(b), resampling both models on the SAME rows.

    This replaces an approximation the research pipeline flagged as a
    limitation. Its `clinical_only_baseline` built the interval on a delta by
    taking "the width of the widest input CI" and centring it on the point
    difference, with the comment:

        # Naive interval on delta: [...] the proper Bayesian comparison needs
        # paired bootstrapping over OOF predictions. Documented limitation.

    That approximation is too wide, because the two models' errors are strongly
    correlated -- they are scored on the identical rows. Resampling the row
    indices ONCE per iteration and evaluating both models on that same
    resample cancels the shared variance and gives an honest interval on the
    difference. `score_a` and `score_b` must be aligned to `y_true`.
    """
    y_true = np.asarray(y_true)
    score_a = np.asarray(score_a)
    score_b = np.asarray(score_b)
    n_obs = y_true.shape[0]

    if not (score_a.shape[0] == score_b.shape[0] == n_obs):
        raise ValueError("y_true, score_a and score_b must be the same length")
    if n_obs < MIN_OBS_FOR_CI:
        return MetricCI(name=name, n=n_obs, note=f"n={n_obs} below minimum for a CI")

    try:
        point = float(metric_fn(y_true, score_a)) - float(metric_fn(y_true, score_b))
    except ValueError as exc:
        return MetricCI(name=name, n=n_obs, note=f"metric undefined: {exc}")

    rng = np.random.default_rng(random_state)
    samples = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, n_obs, n_obs)
        try:
            samples[i] = (
                metric_fn(y_true[idx], score_a[idx])
                - metric_fn(y_true[idx], score_b[idx])
            )
        except ValueError:
            samples[i] = np.nan

    lo, hi = _percentile_ci(samples, ci)
    return MetricCI(value=point, ci_low=lo, ci_high=hi, name=name, n=n_obs)


def bootstrap_stat_ci(
    values: Sequence[float] | np.ndarray,
    stat_fn: Callable[[np.ndarray], float] = np.mean,
    name: str = "",
    n: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_CI,
    random_state: int = 42,
) -> MetricCI:
    """CI on a statistic of one sample -- e.g. a user's mean daily score.

    Used wherever the app reports "your recent average", which until now was a
    bare `sum(scores)/len(scores)` with no indication that seven noisy daily
    scores pin the mean down only loosely.
    """
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    arr = arr[~np.isnan(arr)]
    n_obs = arr.shape[0]

    if n_obs == 0:
        return MetricCI(name=name, n=0, note="no observations")
    if n_obs < MIN_OBS_FOR_CI:
        # Report the point estimate but refuse to invent an interval for it.
        return MetricCI(
            value=float(stat_fn(arr)), name=name, n=n_obs,
            note=f"n={n_obs} below minimum for a CI",
        )

    rng = np.random.default_rng(random_state)
    samples = np.empty(n)
    for i in range(n):
        samples[i] = stat_fn(rng.choice(arr, size=n_obs, replace=True))

    lo, hi = _percentile_ci(samples, ci)
    return MetricCI(
        value=float(stat_fn(arr)), ci_low=lo, ci_high=hi, name=name, n=n_obs,
    )


def bootstrap_delta_ci(
    baseline: Sequence[float] | np.ndarray,
    recent: Sequence[float] | np.ndarray,
    stat_fn: Callable[[np.ndarray], float] = np.mean,
    relative: bool = False,
    name: str = "",
    n: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_CI,
    random_state: int = 42,
) -> MetricCI:
    """CI on (stat(recent) - stat(baseline)), resampling both sides.

    `relative=True` returns the fractional change against baseline, matching
    the app's existing "your score dropped 20%" phrasing -- but now with an
    interval, so a 20% drop measured on four noisy days is visibly not the same
    finding as a 20% drop measured on forty.

    The attention warning should fire on `delta.excludes(0)` and a negative
    point estimate, NOT on the point estimate alone.
    """
    b = np.asarray([v for v in baseline if v is not None], dtype=float)
    r = np.asarray([v for v in recent if v is not None], dtype=float)
    b = b[~np.isnan(b)]
    r = r[~np.isnan(r)]

    if b.shape[0] == 0 or r.shape[0] == 0:
        return MetricCI(name=name, n=0, note="need observations on both sides")

    def _delta(bs: np.ndarray, rs: np.ndarray) -> float:
        b_stat = stat_fn(bs)
        r_stat = stat_fn(rs)
        if relative:
            if b_stat == 0:
                return np.nan
            return float((r_stat - b_stat) / abs(b_stat))
        return float(r_stat - b_stat)

    point = _delta(b, r)
    n_total = b.shape[0] + r.shape[0]

    if min(b.shape[0], r.shape[0]) < MIN_OBS_FOR_CI:
        return MetricCI(
            value=None if np.isnan(point) else point,
            name=name, n=n_total,
            note=(
                f"n_baseline={b.shape[0]}, n_recent={r.shape[0]}; "
                "too few for a CI"
            ),
        )

    rng = np.random.default_rng(random_state)
    samples = np.empty(n)
    for i in range(n):
        bs = rng.choice(b, size=b.shape[0], replace=True)
        rs = rng.choice(r, size=r.shape[0], replace=True)
        samples[i] = _delta(bs, rs)

    lo, hi = _percentile_ci(samples, ci)
    return MetricCI(
        value=None if np.isnan(point) else point,
        ci_low=lo, ci_high=hi, name=name, n=n_total,
    )
