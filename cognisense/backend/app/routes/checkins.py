"""Check-in endpoints: morning (plan + image presentation), midday (light recall), evening (recall + test)."""

import json
import random
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.checkin import MorningCheckin, MiddayCheckin, EveningCheckin
from app.routes.deps import get_user_or_404, get_morning_checkin_or_404
from app.models.image_association import ImageAssociation, seed_associations
from app.schemas import (
    MorningCheckinCreate, MorningCheckinOut, AssociationPresented,
    MiddayCheckinCreate, MiddayCheckinOut,
    EveningCheckinCreate, EveningCheckinOut,
)
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.ml.behavioral_model import activity_overlap, build_behavioral_feature_vector


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

@router.post("/morning", response_model=MorningCheckinOut, status_code=status.HTTP_201_CREATED)
def create_morning_checkin(payload: MorningCheckinCreate, db: Session = Depends(get_db)):
    """Record the user's planned activities and return 5 image associations to remember."""
    user = get_user_or_404(db, payload.user_id)

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
):
    """Optional: attach an audio recording of the user reciting their plans."""
    morning = get_morning_checkin_or_404(db, morning_id)

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
def create_midday_checkin(payload: MiddayCheckinCreate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, payload.user_id)

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

@router.post("/evening", response_model=EveningCheckinOut, status_code=status.HTTP_201_CREATED)
def create_evening_checkin(payload: EveningCheckinCreate, db: Session = Depends(get_db)):
    """Core scoring endpoint. Grades the morning image-association test and computes
    the daily cognitive score via the behavioral model."""
    user = get_user_or_404(db, payload.user_id)

    morning = get_morning_checkin_or_404(db, payload.morning_checkin_id)
    if morning.user_id != user.id:
        raise HTTPException(status_code=403, detail="Morning check-in does not belong to user")

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

    speech_score = morning.speech_biomarker_score if morning.speech_biomarker_score is not None else 0.75

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
        speech_biomarker_score=round(speech_score, 3),
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
