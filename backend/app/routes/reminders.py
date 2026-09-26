"""Reminder endpoints: capture intentions, test recall of them, then help.

Flow the client drives:

  POST /reminders                       user saves something they mean to do
  POST /reminders/{id}/image            optional photo of it
  GET  /reminders/{uid}/due             "is anything due?" -- drives the pop-up
  POST /reminders/{uid}/check           fires the test; returns a prompt ONLY
  POST /reminders/check/{cid}/recall    user's unprompted recall -> graded,
                                        then the full list comes back
  POST /reminders/{uid}/done            tick off what they actually did
  GET  /reminders/{uid}/prospective-score   trend, with intervals

The check endpoint returns no item text by design -- handing the list over
before the recall attempt would defeat the measurement. The recall endpoint
returns the list unconditionally, pass or fail; see app.memory.prospective.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, owned_or_404, require_own_id, require_self
from app.database import get_db
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.memory.prospective import (
    MEMORY_AID_DISCLAIMER,
    MIN_CHECKS_FOR_TREND,
    feedback_message,
    match_recall,
    prospective_memory_summary,
    prospective_trajectory,
)
from app.models.reminder import (
    STATUS_DISMISSED,
    STATUS_DONE,
    STATUS_PENDING,
    ReminderCheck,
    ReminderItem,
)
from app.models.user import User
from app.schemas import (
    ItemMatchOut,
    ProspectiveScoreOut,
    ReminderCheckOut,
    ReminderDoneUpdate,
    ReminderItemCreate,
    ReminderItemOut,
    ReminderRecallResultOut,
    ReminderRecallSubmit,
)

router = APIRouter(prefix="/reminders", tags=["reminders"])

IMAGE_DIR = Path(__file__).resolve().parent.parent / "db" / "reminders"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024

RECALL_PROMPT = (
    "Without looking at your list -- what did you mean to do? "
    "Name at least one thing you can remember."
)


def _active_items(db: Session, user_id: int) -> list[ReminderItem]:
    return (
        db.query(ReminderItem)
        .filter(ReminderItem.user_id == user_id)
        .filter(ReminderItem.status == STATUS_PENDING)
        .order_by(ReminderItem.created_at.asc())
        .all()
    )


# =============================================================================
# CAPTURE
# =============================================================================

@router.post("", response_model=ReminderItemOut, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: ReminderItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save something the user intends to do."""
    require_own_id(payload.user_id, current_user)

    item = ReminderItem(
        user_id=current_user.id,
        description=(payload.description or "").strip() or None,
        label=(payload.label or "").strip() or None,
        due_at=payload.due_at,
        status=STATUS_PENDING,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/image", response_model=ReminderItemOut)
async def upload_reminder_image(
    item_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach a photo of the thing to be done.

    The stored filename is derived from the item id plus a validated extension.
    The client-supplied filename is never used in the path -- it is attacker
    controlled and would otherwise allow directory traversal.
    """
    # Keyed by item id, so authentication alone is not enough: without this
    # ownership check any logged-in user could overwrite the photo on someone
    # else's reminder by guessing an id.
    item = owned_or_404(
        db.query(ReminderItem).filter(ReminderItem.id == item_id).first(),
        current_user, "Reminder",
    )

    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image type {suffix or '(none)'}; "
                   f"allowed: {sorted(ALLOWED_IMAGE_SUFFIXES)}",
        )

    body = await image.read()
    if len(body) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image larger than 12 MB")

    path = IMAGE_DIR / f"item_{item_id}{suffix}"
    path.write_bytes(body)

    item.image_path = str(path)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{user_id}", response_model=list[ReminderItemOut])
def list_reminders(
    user_id: int,
    status_filter: str = Query(STATUS_PENDING, pattern="^(pending|done|dismissed|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    q = db.query(ReminderItem).filter(ReminderItem.user_id == user_id)
    if status_filter != "all":
        q = q.filter(ReminderItem.status == status_filter)
    return q.order_by(ReminderItem.created_at.desc()).all()


@router.get("/{user_id}/due", response_model=list[ReminderItemOut])
def due_reminders(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Outstanding items that are due now.

    Items with no due date are always considered due, so a user who never sets
    times still gets checked.

    NOTE: this only answers the question; it prompts nobody. Prompting happens
    through Web Push -- app/notifications/scheduler.py applies the same "due"
    rule and sends a notification that deliberately does not name the items.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(ReminderItem)
        .filter(ReminderItem.user_id == user_id)
        .filter(ReminderItem.status == STATUS_PENDING)
        .filter(or_(ReminderItem.due_at.is_(None), ReminderItem.due_at <= now))
        .order_by(ReminderItem.created_at.asc())
        .all()
    )


# =============================================================================
# THE CHECK
# =============================================================================

@router.post("/{user_id}/check", response_model=ReminderCheckOut,
             status_code=status.HTTP_201_CREATED)
def start_check(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Fire a prospective-memory check. Returns the prompt and nothing else."""
    items = _active_items(db, user_id)
    if not items:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "nothing_to_check",
                "message": "There is nothing on the list to be tested on.",
            },
        )

    check = ReminderCheck(
        user_id=user_id,
        active_item_ids=[i.id for i in items],
        n_items_active=len(items),
    )
    db.add(check)
    db.commit()
    db.refresh(check)

    return ReminderCheckOut(
        check_id=check.id,
        triggered_at=check.triggered_at,
        n_items_active=check.n_items_active,
        prompt=RECALL_PROMPT,
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
    )


@router.post("/check/{check_id}/recall", response_model=ReminderRecallResultOut)
def submit_recall(
    check_id: int,
    payload: ReminderRecallSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grade the unprompted recall, then hand back the full list regardless."""
    # Keyed by check id. Without the ownership check, answering someone else's
    # check would return THEIR reminder list in the response -- the aid step
    # hands back every item, so this route leaks the most on a missing check.
    check = owned_or_404(
        db.query(ReminderCheck).filter(ReminderCheck.id == check_id).first(),
        current_user, "Check",
    )
    if check.responded_at is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "already_answered",
                "message": "This check has already been answered.",
            },
        )

    items = (
        db.query(ReminderItem)
        .filter(ReminderItem.id.in_(check.active_item_ids or []))
        .order_by(ReminderItem.created_at.asc())
        .all()
    )

    result = match_recall(payload.recall_text, items)

    check.responded_at = datetime.now(timezone.utc)
    check.recall_text = payload.recall_text
    check.matched_item_ids = result.matched_item_ids
    check.n_recalled = result.n_recalled
    check.passed = result.passed
    check.prospective_score = result.prospective_score
    check.aid_shown = result.show_aid
    check.response_latency_ms = payload.response_latency_ms
    db.commit()

    return ReminderRecallResultOut(
        check_id=check.id,
        n_active=result.n_active,
        n_recalled=result.n_recalled,
        passed=result.passed,
        prospective_score=result.prospective_score,
        feedback=feedback_message(result),
        matches=[ItemMatchOut(**vars(m)) for m in result.matches],
        # Always returned -- the aid is not withheld on a failed attempt.
        items=[ReminderItemOut.model_validate(i) for i in items],
        disclaimer=NON_DIAGNOSTIC_DISCLAIMER,
        memory_aid_disclaimer=MEMORY_AID_DISCLAIMER,
    )


@router.post("/{user_id}/done", response_model=list[ReminderItemOut])
def mark_done(
    user_id: int,
    payload: ReminderDoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Tick off what the user reports having actually done."""
    items = (
        db.query(ReminderItem)
        .filter(ReminderItem.user_id == user_id)
        .filter(ReminderItem.id.in_(payload.item_ids))
        .all()
    )
    if len(items) != len(set(payload.item_ids)):
        raise HTTPException(
            status_code=404, detail="one or more reminders not found for this user"
        )

    now = datetime.now(timezone.utc)
    for item in items:
        item.status = STATUS_DONE
        item.completed_at = now

    # Attribute the completions to the most recent answered check, so "recalled"
    # and "done" stay separable in the record.
    latest = (
        db.query(ReminderCheck)
        .filter(ReminderCheck.user_id == user_id)
        .filter(ReminderCheck.responded_at.isnot(None))
        .order_by(ReminderCheck.responded_at.desc())
        .first()
    )
    if latest is not None:
        latest.reported_done_item_ids = list(payload.item_ids)
        latest.n_reported_done = len(payload.item_ids)

    db.commit()
    return items


@router.post("/{user_id}/dismiss", response_model=list[ReminderItemOut])
def dismiss(
    user_id: int,
    payload: ReminderDoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Drop items the user no longer intends to do, without scoring them as done."""
    items = (
        db.query(ReminderItem)
        .filter(ReminderItem.user_id == user_id)
        .filter(ReminderItem.id.in_(payload.item_ids))
        .all()
    )
    for item in items:
        item.status = STATUS_DISMISSED
    db.commit()
    return items


# =============================================================================
# TREND
# =============================================================================

@router.get("/{user_id}/prospective-score", response_model=ProspectiveScoreOut)
def prospective_score(
    user_id: int,
    window_days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Prospective-recall rate with a 95% interval, and the trend if earned."""
    checks = (
        db.query(ReminderCheck)
        .filter(ReminderCheck.user_id == user_id)
        .filter(ReminderCheck.prospective_score.isnot(None))
        .order_by(ReminderCheck.responded_at.asc())
        .all()
    )
    n_checks = len(checks)

    if n_checks == 0:
        return ProspectiveScoreOut(
            n_checks=0,
            trend_available=False,
            trend_note="No answered checks yet.",
            memory_aid_disclaimer=MEMORY_AID_DISCLAIMER,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    recent = [
        c.prospective_score for c in checks
        if c.responded_at and c.responded_at.replace(tzinfo=timezone.utc) >= cutoff
    ] or [checks[-1].prospective_score]
    baseline = [
        c.prospective_score for c in checks
        if c.responded_at and c.responded_at.replace(tzinfo=timezone.utc) < cutoff
    ]

    summary = prospective_memory_summary(recent)

    out = ProspectiveScoreOut(
        n_checks=n_checks,
        recall_rate=summary.value,
        recall_rate_ci_low=summary.ci_low,
        recall_rate_ci_high=summary.ci_high,
        trend_available=False,
        memory_aid_disclaimer=MEMORY_AID_DISCLAIMER,
    )

    # Same bar as the retrospective side: no trend claim without enough checks.
    if n_checks < MIN_CHECKS_FOR_TREND or not baseline:
        out.trend_note = (
            f"{n_checks} check(s) so far. A trend needs at least "
            f"{MIN_CHECKS_FOR_TREND}, with some history before the last "
            f"{window_days} days."
        )
        return out

    change = prospective_trajectory(baseline, recent)
    out.trend_available = change.is_estimable
    if change.is_estimable:
        out.change_pct = round(change.value * 100, 1)
        out.change_ci_low_pct = round(change.ci_low * 100, 1)
        out.change_ci_high_pct = round(change.ci_high * 100, 1)
        out.trend_note = (
            "This change is larger than day-to-day variation."
            if change.excludes(0.0)
            else "This is within normal day-to-day variation."
        )
    else:
        out.trend_note = "Not enough answered checks on both sides to compare yet."
    return out
