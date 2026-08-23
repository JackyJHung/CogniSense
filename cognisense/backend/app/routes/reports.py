"""Reports and risk-comparison endpoints."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.checkin import EveningCheckin
from app.routes.deps import get_user_or_404
from app.schemas import RiskComparisonOut, DailySuggestionsOut
from app.data.research_benchmarks import (
    LANCET_2024_RISK_FACTORS,
    NON_DIAGNOSTIC_DISCLAIMER,
)
from app.ml.risk_comparison import build_risk_comparison, personalized_suggestions


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/risk-comparison/{user_id}", response_model=RiskComparisonOut)
def get_risk_comparison(
    user_id: int,
    window_days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """
    Compare user's recent cognitive scores (last `window_days` days) against
    their own earlier baseline AND against age/gender/race research benchmarks.
    """
    user = get_user_or_404(db, user_id)

    cutoff = datetime.utcnow() - timedelta(days=window_days)

    recent_rows = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.user_id == user_id)
        .filter(EveningCheckin.timestamp >= cutoff)
        .filter(EveningCheckin.daily_cognitive_score.isnot(None))
        .order_by(EveningCheckin.timestamp.desc())
        .all()
    )

    baseline_rows = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.user_id == user_id)
        .filter(EveningCheckin.timestamp < cutoff)
        .filter(EveningCheckin.daily_cognitive_score.isnot(None))
        .order_by(EveningCheckin.timestamp.asc())
        .limit(14)
        .all()
    )

    recent_scores = [r.daily_cognitive_score for r in recent_rows]
    baseline_scores = [r.daily_cognitive_score for r in baseline_rows]

    # If we have fewer than 3 recent scores, just show benchmarks with no trajectory analysis
    if not recent_scores:
        recent_scores = [user.cumulative_recall_score or 0.0]
    if not baseline_scores:
        baseline_scores = recent_scores

    payload = build_risk_comparison(
        age=user.age,
        gender=user.gender,
        race=user.race,
        recent_scores=recent_scores,
        baseline_scores=baseline_scores,
        total_checkins=user.cumulative_checkin_count,
    )
    return RiskComparisonOut(**payload)


@router.get("/daily-suggestions/{user_id}", response_model=DailySuggestionsOut)
def get_daily_suggestions(user_id: int, db: Session = Depends(get_db)):
    """Return 3 research-backed daily prevention suggestions personalized by age."""
    user = get_user_or_404(db, user_id)

    suggestions = personalized_suggestions(user.age, elevated_concern=False, n=3)

    return DailySuggestionsOut(
        suggestions=suggestions,
        lancet_risk_factor_source=(
            "Livingston G et al. Dementia prevention, intervention, and care: "
            "2024 report of the Lancet standing Commission. Lancet 404(10452):572-628."
        ),
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.get("/trend/{user_id}")
def get_trend(
    user_id: int,
    days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
):
    """Return a time series of daily cognitive scores for charting."""
    get_user_or_404(db, user_id)

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.user_id == user_id)
        .filter(EveningCheckin.timestamp >= cutoff)
        .order_by(EveningCheckin.timestamp.asc())
        .all()
    )

    return {
        "user_id": user_id,
        "window_days": days,
        "series": [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "daily_cognitive_score": r.daily_cognitive_score,
                "association_accuracy": r.association_accuracy,
                "activity_recall_accuracy": r.activity_recall_accuracy,
                "avg_response_latency_ms": r.avg_response_latency_ms,
            }
            for r in rows
        ],
        "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
    }
