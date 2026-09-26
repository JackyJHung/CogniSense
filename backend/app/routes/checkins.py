"""Check-in endpoints: morning (plan + image presentation), midday (light recall), evening (recall + test)."""

import random
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, owned_or_404, require_own_id, require_self
from app.database import get_db
from app.models.user import User
from app.models.checkin import MorningCheckin, MiddayCheckin, EveningCheckin
from app.models.image_association import ImageAssociation, seed_associations
from app.schemas import (
    MorningCheckinCreate, MorningCheckinOut, AssociationPresented,
    MiddayCheckinCreate, MiddayCheckinOut,
    EveningCheckinCreate, EveningCheckinOut,
)
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.ml.behavioral_model import activity_overlap, build_behavioral_feature_vector
from app.timezones import day_bounds_utc, local_date, zone_for


router = APIRouter(prefix="/checkins", tags=["checkins"])

# Audio upload storage
AUDIO_DIR = Path(__file__).resolve().parent.parent / "db" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

N_ASSOCIATIONS = 5   # Images shown in the morning and tested in the evening


# Lazy ML model loading
_speech_scorer = None
_behavioral_scorer = None


def _get_speech_scorer():
    global _speech_scorer
    if _speech_scorer is None:
        from app.ml.speech_model import SpeechScorer
        _speech_scorer = SpeechScorer()
    return _speech_scorer


def _get_behavioral_scorer():
    global _behavioral_scorer
    if _behavioral_scorer is None:
        from app.ml.behavioral_model import BehavioralScorer
        _behavioral_scorer = BehavioralScorer()
    return _behavioral_scorer


# =============================================================================
# MORNING
# =============================================================================

def _now() -> datetime:
    """The current instant; a function so tests can pin the clock."""
    return datetime.now(timezone.utc)


def _today_bounds(
    now_utc: Optional[datetime] = None, zone: tzinfo = timezone.utc,
) -> tuple[datetime, datetime]:
    """Return [start, end) of the current day in `zone`, as naive UTC datetimes.

    BUG THIS FIXES. This used to build the window from `date.today()` -- the
    server's LOCAL date -- and compare it against `timestamp` columns, which
    SQLite fills from `func.now()` in UTC and returns naive. Whenever the local
    date and the UTC date disagree, the window pointed at the wrong day and the
    query below found nothing.

    On this machine (UTC-7) that is every evening from 17:00 local onward: a
    morning check-in submitted at 18:00 local stores 01:00 UTC the NEXT day,
    lands outside a window built from the local date, and so:
      - the duplicate guard silently stops working, letting a user roll a fresh
        set of image associations and grade the evening test against the wrong
        morning -- the exact thing the 409 exists to prevent; and
      - GET /checkins/morning/today/{user_id} returns 404 for a check-in that
        does exist.

    Naive UTC is returned deliberately, because that is precisely the form
    SQLite stores and hands back -- see the probe in the commit that introduced
    this. Mixing an aware datetime into the comparison would work, but keeping
    both sides in one representation is what makes the code readable.

    THE DAY IS THE USER'S OWN. `zone` is the user's IANA time zone (see
    app/timezones.py), so the day turns over at their local midnight. A UTC day
    turned over at 17:00 for somebody in Los Angeles, which filed every evening
    check-in under the next day. Across a DST change the day is 23 or 25 hours
    long. An account whose zone is not known yet is counted in UTC, as before.
    """
    now = now_utc or _now()
    return day_bounds_utc(local_date(now, zone), zone)


def _morning_to_out(morning: MorningCheckin) -> MorningCheckinOut:
    return MorningCheckinOut(
        id=morning.id,
        timestamp=morning.timestamp,
        planned_activities=morning.planned_activities,
        presented_associations=[AssociationPresented(**p) for p in morning.presented_associations],
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.get("/morning/today/{user_id}", response_model=MorningCheckinOut)
def get_today_morning(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Fetch today's morning check-in for a user, if one exists. 404 if not yet submitted today."""
    start, end = _today_bounds(zone=zone_for(current_user))
    morning = (
        db.query(MorningCheckin)
        .filter(MorningCheckin.user_id == user_id)
        .filter(MorningCheckin.timestamp >= start)
        .filter(MorningCheckin.timestamp < end)
        .first()
    )
    if not morning:
        raise HTTPException(status_code=404, detail="No morning check-in yet today")
    return _morning_to_out(morning)


@router.post("/morning", response_model=MorningCheckinOut, status_code=status.HTTP_201_CREATED)
def create_morning_checkin(
    payload: MorningCheckinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record the user's planned activities and return 5 image associations to remember.

    Enforces ONE morning check-in per user per day. A second POST on the same day returns 409
    with the existing record echoed in the error detail so clients can render it without an
    extra round-trip.
    """
    user = require_own_id(payload.user_id, current_user)

    # Block duplicate morning check-ins on the same calendar day -- the user's
    # own, in their time zone. Once submitted, the associations are locked so the
    # evening test grades against the original morning rather than a
    # freshly-rolled set.
    start, end = _today_bounds(zone=zone_for(user))
    existing = (
        db.query(MorningCheckin)
        .filter(MorningCheckin.user_id == user.id)
        .filter(MorningCheckin.timestamp >= start)
        .filter(MorningCheckin.timestamp < end)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "morning_already_submitted",
                "message": "Morning check-in already submitted today.",
                "existing": _morning_to_out(existing).model_dump(mode="json"),
            },
        )

    # Ensure the image pool is seeded
    seed_associations(db)

    all_assocs = db.query(ImageAssociation).all()
    if len(all_assocs) < N_ASSOCIATIONS:
        raise HTTPException(status_code=500, detail="Image-association pool is under-seeded")

    chosen = random.sample(all_assocs, N_ASSOCIATIONS)
    presented_payload = [
        {"id": a.id, "object_name": a.object_name, "cue_word": a.cue_word, "image_path": a.image_path}
        for a in chosen
    ]

    morning = MorningCheckin(
        user_id=user.id,
        planned_activities=payload.planned_activities,
        presented_associations=presented_payload,
    )
    db.add(morning)
    db.commit()
    db.refresh(morning)

    return MorningCheckinOut(
        id=morning.id,
        timestamp=morning.timestamp,
        planned_activities=morning.planned_activities,
        presented_associations=[AssociationPresented(**p) for p in presented_payload],
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.post("/morning/{morning_id}/audio", status_code=status.HTTP_200_OK)
async def upload_morning_audio(
    morning_id: int,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Optional: attach an audio recording of the user reciting their plans."""
    # Keyed by morning_id: authentication alone would still let any logged-in
    # user attach a recording to someone else's check-in, and have it scored
    # into that person's speech biomarker.
    morning = owned_or_404(
        db.query(MorningCheckin).filter(MorningCheckin.id == morning_id).first(),
        current_user, "Morning check-in",
    )

    file_path = AUDIO_DIR / f"morning_{morning_id}_{audio.filename}"
    with open(file_path, "wb") as f:
        f.write(await audio.read())

    try:
        speech_score = _get_speech_scorer().score_audio(file_path)
    except Exception as e:
        speech_score = None
        print(f"[speech] scoring failed for morning {morning_id}: {e}")

    morning.audio_file_path = str(file_path)
    morning.speech_biomarker_score = speech_score
    db.commit()
    return {"speech_biomarker_score": speech_score, "disclaimer": NON_DIAGNOSTIC_DISCLAIMER}


# =============================================================================
# MIDDAY
# =============================================================================

@router.post("/midday", response_model=MiddayCheckinOut, status_code=status.HTTP_201_CREATED)
def create_midday_checkin(
    payload: MiddayCheckinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append a midday check-in.

    INTENTIONALLY append-only — each POST creates a new row. Users may submit multiple midday
    check-ins per day (e.g. one before lunch, one after) and earlier entries are preserved as
    part of the longitudinal record. Do NOT add an "upsert-by-day" guard here.
    """
    user = require_own_id(payload.user_id, current_user)

    # If a morning is referenced it must be the caller's own, so a midday row
    # cannot be hung off someone else's check-in.
    if payload.morning_checkin_id is not None:
        owned_or_404(
            db.query(MorningCheckin).filter(
                MorningCheckin.id == payload.morning_checkin_id
            ).first(),
            current_user, "Morning check-in",
        )

    mc = MiddayCheckin(
        user_id=user.id,
        morning_checkin_id=payload.morning_checkin_id,
        what_user_has_done=payload.what_user_has_done,
        planned_remainder=payload.planned_remainder,
        response_latency_ms=payload.response_latency_ms,
    )
    db.add(mc)
    db.commit()
    db.refresh(mc)

    return MiddayCheckinOut(
        id=mc.id,
        timestamp=mc.timestamp,
        what_user_has_done=mc.what_user_has_done,
        planned_remainder=mc.planned_remainder,
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


# =============================================================================
# EVENING
# =============================================================================

def _evening_to_out(evening: EveningCheckin) -> EveningCheckinOut:
    return EveningCheckinOut(
        id=evening.id,
        timestamp=evening.timestamp,
        activity_recall_accuracy=evening.activity_recall_accuracy,
        association_accuracy=evening.association_accuracy,
        avg_response_latency_ms=evening.avg_response_latency_ms,
        daily_cognitive_score=evening.daily_cognitive_score,
        behavioral_biomarker_score=evening.behavioral_biomarker_score,
        speech_biomarker_score=evening.speech_biomarker_score,
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.post("/evening", response_model=EveningCheckinOut, status_code=status.HTTP_201_CREATED)
def create_evening_checkin(
    payload: EveningCheckinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Core scoring endpoint. Grades the morning image-association test and computes
    the daily cognitive score via the behavioral model.

    Enforces ONE evening test per morning check-in. A second POST returns 409 with
    the first result echoed in the error detail, as the morning's 409 does.
    """
    user = require_own_id(payload.user_id, current_user)

    # This route already checked that the morning belonged to the claimed user --
    # but the claimed user was itself unverified, so the check could be satisfied
    # by simply claiming to be the morning's owner. Now the identity is proven
    # first, and owned_or_404 re-states the ownership requirement against it.
    morning = owned_or_404(
        db.query(MorningCheckin).filter(
            MorningCheckin.id == payload.morning_checkin_id
        ).first(),
        current_user, "Morning check-in",
    )

    # A retake has already seen the answers, so it measures nothing new. It used
    # to be scored anyway: stored beside the first attempt, added to
    # cumulative_checkin_count (which feeds the consistency feature of every
    # later score), and shown as the day's result -- while the reports, rightly,
    # count only the first attempt. The first attempt is the result, so that is
    # what a second submission gets back.
    first_attempt = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.morning_checkin_id == morning.id)
        .order_by(EveningCheckin.timestamp.asc(), EveningCheckin.id.asc())
        .first()
    )
    if first_attempt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "evening_already_submitted",
                "message": "This evening's test has already been taken.",
                "existing": _evening_to_out(first_attempt).model_dump(mode="json"),
            },
        )

    # -------- Grade image-association test --------
    presented = {p["id"]: p for p in morning.presented_associations}
    graded = []
    latencies = []
    correct_count = 0

    for resp in payload.association_responses:
        expected = presented.get(resp.association_id)
        if expected is None:
            raise HTTPException(
                status_code=400,
                detail=f"Association {resp.association_id} was not presented this morning",
            )
        is_correct = resp.user_answer.strip().lower() == expected["object_name"].strip().lower()
        if is_correct:
            correct_count += 1
        latencies.append(resp.response_latency_ms)
        graded.append({
            "association_id": resp.association_id,
            "cue_word": expected["cue_word"],
            "expected_answer": expected["object_name"],
            "user_answer": resp.user_answer,
            "correct": is_correct,
            "response_latency_ms": resp.response_latency_ms,
        })

    assoc_accuracy = correct_count / max(len(graded), 1)
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    # -------- Grade activity recall --------
    act_recall_accuracy = activity_overlap(morning.planned_activities, payload.recalled_activities)

    # -------- Behavioral biomarker score --------
    # For baseline latency, use the user's rolling average when available; otherwise 1500ms default
    prior_evenings = (
        db.query(EveningCheckin)
        .filter(EveningCheckin.user_id == user.id)
        .filter(EveningCheckin.avg_response_latency_ms.isnot(None))
        .order_by(EveningCheckin.timestamp.asc())
        .limit(14)
        .all()
    )
    baseline_latency = (
        int(sum(e.avg_response_latency_ms for e in prior_evenings) / len(prior_evenings))
        if prior_evenings else 1500
    )

    checkin_consistency = min(user.cumulative_checkin_count + 1, 30) / 30.0

    # Latency variance within this evening's test
    if len(latencies) >= 2:
        mean_l = sum(latencies) / len(latencies)
        var = sum((l - mean_l) ** 2 for l in latencies) / len(latencies)
        # Normalize by mean^2 => unitless, then clip
        lat_var = min(var / (mean_l ** 2 + 1), 1.0) if mean_l > 0 else 0.0
    else:
        lat_var = 0.0

    # No client records audio yet, so there is usually no speech measurement.
    # The composite still needs a value in that slot, and a neutral 0.75 stands
    # in -- but only inside the calculation. What is stored and shown as the
    # speech biomarker is the measurement or nothing: a placeholder presented
    # as a result would be a number nobody measured.
    speech_measured = morning.speech_biomarker_score
    speech_score = speech_measured if speech_measured is not None else 0.75

    feats = build_behavioral_feature_vector(
        activity_recall_accuracy=act_recall_accuracy,
        association_accuracy=assoc_accuracy,
        avg_response_latency_ms=avg_latency,
        baseline_latency_ms=baseline_latency,
        recalled_text=payload.recalled_activities,
        latency_variance=lat_var,
        checkin_consistency=checkin_consistency,
        speech_biomarker_score=speech_score,
    )

    try:
        behav_score = _get_behavioral_scorer().score(feats)
    except Exception as e:
        print(f"[behav] scoring failed: {e}")
        # Fallback heuristic if model not yet trained
        behav_score = 0.5 * assoc_accuracy + 0.3 * act_recall_accuracy + 0.2 * speech_score

    # Composite daily score: weighted average of association accuracy, behavioral model, speech
    daily_score = round(
        0.45 * behav_score + 0.35 * assoc_accuracy + 0.20 * speech_score,
        3,
    )

    # -------- Persist --------
    evening = EveningCheckin(
        user_id=user.id,
        morning_checkin_id=morning.id,
        recalled_activities=payload.recalled_activities,
        activity_recall_accuracy=round(act_recall_accuracy, 3),
        association_responses=graded,
        association_accuracy=round(assoc_accuracy, 3),
        avg_response_latency_ms=avg_latency,
        behavioral_biomarker_score=round(behav_score, 3),
        speech_biomarker_score=None if speech_measured is None else round(speech_measured, 3),
        daily_cognitive_score=daily_score,
    )
    db.add(evening)

    # Update user rolling aggregates
    user.cumulative_recall_score = (
        (user.cumulative_recall_score * user.cumulative_checkin_count + daily_score)
        / (user.cumulative_checkin_count + 1)
    )
    user.cumulative_checkin_count = user.cumulative_checkin_count + 1

    db.commit()
    db.refresh(evening)

    return _evening_to_out(evening)
