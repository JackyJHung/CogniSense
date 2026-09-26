"""Reports and risk-comparison endpoints.

Both the risk report and the trend read one score per local day
(app/daily_scores.py) in the user's own time zone, and both judge a period with
the same trajectory analysis, so for the same window they cannot disagree.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_self
from app.daily_scores import (
    ROLLING_DAYS,
    daily_points,
    load_day_scores,
    period_bounds_utc,
    split_period,
)
from app.database import get_db
from app.models.user import User
from app.models.checkin import EveningCheckin
from app.schemas import DailySuggestionsOut, RiskComparisonOut, TrendOut, TrendPoint
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.ml.risk_comparison import (
    analyze_trajectory,
    build_risk_comparison,
    personalized_suggestions,
)
from app.timezones import local_date, zone_for


router = APIRouter(prefix="/reports", tags=["reports"])


def _now() -> datetime:
    """The current instant; a function so tests can pin the clock."""
    return datetime.now(timezone.utc)


def _pct(value):
    return None if value is None else round(value * 100, 1)


@router.get("/risk-comparison/{user_id}", response_model=RiskComparisonOut)
def get_risk_comparison(
    user_id: int,
    window_days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """
    Compare user's recent cognitive scores (last `window_days` days) against
    their own earlier baseline AND against age/gender/race research benchmarks.
    """
    user = current_user
    zone = zone_for(user)
    days = load_day_scores(db, user.id, zone)
    period = split_period(days, local_date(_now(), zone), window_days)

    # Passed as they are, empty or not. This used to stand in the user's
    # all-time average for an empty period -- shown as "your recent average:
    # 0%" to every new account -- and the period itself for a missing
    # baseline, which compared it with itself and reported no change. Both are
    # "can't tell yet", and analyze_trajectory now says so.
    payload = build_risk_comparison(
        age=user.age,
        gender=user.gender,
        race=user.race,
        recent_scores=period.recent,
        baseline_scores=period.baseline,
        total_checkins=period.scored_days,
    )
    return RiskComparisonOut(**payload)


@router.get("/daily-suggestions/{user_id}", response_model=DailySuggestionsOut)
def get_daily_suggestions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Return 3 research-backed daily prevention suggestions personalized by age."""
    suggestions = personalized_suggestions(current_user.age, elevated_concern=False, n=3)

    return DailySuggestionsOut(
        suggestions=suggestions,
        lancet_risk_factor_source=(
            "Livingston G et al. Dementia prevention, intervention, and care: "
            "2024 report of the Lancet standing Commission. Lancet 404(10452):572-628."
        ),
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.get("/trend/{user_id}", response_model=TrendOut)
def get_trend(
    user_id: int,
    days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Daily scores for the last `days` local days, with intervals.

    It used to return the raw evening rows: bare scores with no interval, no
    baseline, no gaps, and no way to tell "fine" from "too little data" --
    everything the rest of the app refuses to show. Every day in the window
    now has a point (a day without a check-in has no score, never a zero), the
    band is the 95% interval on the trailing mean, and the summary is the risk
    report's own trajectory analysis on the same inputs.
    """
    user = current_user
    zone = zone_for(user)
    day_scores = load_day_scores(db, user.id, zone)
    period = split_period(day_scores, local_date(_now(), zone), days)
    traj = analyze_trajectory(period.recent, period.baseline, period.scored_days)

    points = [
        TrendPoint(
            date=p.day,
            score=None if p.score is None else round(p.score, 3),
            attempts=p.attempts,
            rolling_mean=None if p.rolling.value is None else round(p.rolling.value, 3),
            rolling_ci_low=None if p.rolling.ci_low is None else round(p.rolling.ci_low, 3),
            rolling_ci_high=None if p.rolling.ci_high is None else round(p.rolling.ci_high, 3),
            rolling_scored_days=p.rolling.n,
        )
        for p in daily_points(day_scores, period.first_day, period.last_day)
    ]

    start, end = period_bounds_utc(period.first_day, period.last_day, zone)
    rows = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.user_id == user.id)
        .filter(EveningCheckin.timestamp >= start)
        .filter(EveningCheckin.timestamp < end)
        .order_by(EveningCheckin.timestamp.asc())
        .all()
    )

    return TrendOut(
        user_id=user.id,
        window_days=days,
        timezone=user.timezone or "UTC",
        rolling_days=ROLLING_DAYS,
        points=points,
        n_scored_days=traj.current.n,
        recent_avg=traj.current.value,
        recent_avg_ci_low=traj.current.ci_low,
        recent_avg_ci_high=traj.current.ci_high,
        baseline_avg=traj.baseline.value,
        baseline_ci_low=traj.baseline.ci_low,
        baseline_ci_high=traj.baseline.ci_high,
        baseline_days=traj.baseline.n,
        change_pct=_pct(traj.change.value),
        change_ci_low_pct=_pct(traj.change.ci_low),
        change_ci_high_pct=_pct(traj.change.ci_high),
        elevated_concern=traj.elevated_concern,
        concern_reason=traj.reason,
        inconclusive=traj.inconclusive,
        inconclusive_reason=traj.inconclusive_reason,
        series=[
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "daily_cognitive_score": r.daily_cognitive_score,
                "association_accuracy": r.association_accuracy,
                "activity_recall_accuracy": r.activity_recall_accuracy,
                "avg_response_latency_ms": r.avg_response_latency_ms,
            }
            for r in rows
        ],
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )
