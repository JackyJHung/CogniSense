"""The background loop that pushes reminder checks without anyone opening the app.

This is the piece that makes the feature work when the app is closed. It runs
inside the FastAPI process, wakes every `TICK_SECONDS`, and for each user with a
registered device decides whether now is a reasonable moment to prompt them.

WHAT "CLOSED" ACTUALLY MEANS -- read this before promising anything to a user:

  tab closed          works. The service worker is woken by the push service.
  browser closed      desktop: only if the browser keeps a background process
                      alive (Chrome: Settings > System > "Continue running
                      background apps when Google Chrome is closed"). Android:
                      works regardless. iOS: only for a PWA installed to the
                      home screen, iOS 16.4+.
  backend stopped     nothing is sent. This loop is the sender; if the server
                      is not running there is no scheduler.

So "even if the app is closed" is true for the app, and true for the browser on
mobile. It is not magic: some process has to be alive on each end.

THREE RULES KEEP THIS FROM BECOMING SPAM
  1. cooldown   at most one push per user per COOLDOWN_HOURS
  2. quiet hours never between the user's sleep_time and wake_time
  3. something to say  no pending, due reminders means no push
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.push import PushSubscription
from app.models.reminder import STATUS_PENDING, ReminderItem
from app.models.user import User
from app.notifications.sender import notify_user

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


TICK_SECONDS = _env_int("COGNISENSE_PUSH_TICK_SECONDS", 60)
COOLDOWN_HOURS = _env_int("COGNISENSE_PUSH_COOLDOWN_HOURS", 6)

# Set COGNISENSE_DISABLE_SCHEDULER=1 to keep the loop out of the way -- tests
# set it so a background thread cannot touch the database mid-assertion.
DISABLED = os.environ.get("COGNISENSE_DISABLE_SCHEDULER", "").strip() in {"1", "true", "yes"}


def is_awake(user: User, now_utc: datetime | None = None) -> bool:
    """Is it currently inside this user's waking hours?

    `utc_offset_minutes` comes from the browser at subscribe time. It defaults
    to 0, which for a user who has never subscribed would mean UTC -- but such a
    user has no devices to push to anyway, so the default never decides anything
    real.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    local = now_utc + timedelta(minutes=user.utc_offset_minutes or 0)
    now_t = local.time()

    wake, sleep = user.wake_time, user.sleep_time
    if wake is None or sleep is None:
        return True
    if wake <= sleep:
        return wake <= now_t <= sleep
    # Sleep time is past midnight, e.g. wake 07:00, sleep 01:00.
    return now_t >= wake or now_t <= sleep


def _due_pending_count(db: Session, user_id: int, now_naive_utc: datetime) -> int:
    """Pending items whose due time has arrived. No due date means always due."""
    return (
        db.query(ReminderItem)
        .filter(ReminderItem.user_id == user_id)
        .filter(ReminderItem.status == STATUS_PENDING)
        .filter(or_(ReminderItem.due_at.is_(None), ReminderItem.due_at <= now_naive_utc))
        .count()
    )


def build_payload(n_due: int) -> dict:
    """What the service worker renders. Deliberately says nothing specific.

    The notification is a prompt to recall, so naming the items on the lock
    screen would hand over the answers -- and would also put a person's errands
    in front of anyone glancing at their phone.
    """
    plural = "" if n_due == 1 else "s"
    return {
        "title": "What did you mean to do?",
        "body": (
            f"You have {n_due} thing{plural} saved. "
            f"Tap to see how many you can remember."
        ),
        "tag": "cognisense-reminder-check",
        "url": "/reminders",
    }


def run_tick(db: Session, now_utc: datetime | None = None) -> dict:
    """One pass over all users with devices. Returns a summary for logging/tests."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_naive = now_utc.replace(tzinfo=None)
    cutoff = now_utc - timedelta(hours=COOLDOWN_HOURS)

    user_ids = [
        row[0]
        for row in db.query(PushSubscription.user_id).distinct().all()
    ]
    summary = {"considered": len(user_ids), "pushed": 0, "asleep": 0,
               "cooling_down": 0, "nothing_due": 0}

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            continue

        if user.last_push_at is not None:
            last = user.last_push_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last > cutoff:
                summary["cooling_down"] += 1
                continue

        if not is_awake(user, now_utc):
            summary["asleep"] += 1
            continue

        n_due = _due_pending_count(db, user_id, now_naive)
        if n_due == 0:
            summary["nothing_due"] += 1
            continue

        result = notify_user(db, user_id, build_payload(n_due))
        if result["sent"] > 0:
            user.last_push_at = now_utc
            db.commit()
            summary["pushed"] += 1

    return summary


async def _loop() -> None:
    logger.info(
        "reminder push scheduler started (tick=%ss, cooldown=%sh)",
        TICK_SECONDS, COOLDOWN_HOURS,
    )
    while True:
        try:
            # webpush() and the ORM are blocking; keep them off the event loop
            # or every push stalls the API.
            await asyncio.to_thread(_tick_with_session)
        except asyncio.CancelledError:
            logger.info("reminder push scheduler stopping")
            raise
        except Exception:
            # A scheduler that dies on one bad row stops notifying everyone.
            logger.exception("push scheduler tick failed; continuing")
        await asyncio.sleep(TICK_SECONDS)


def _tick_with_session() -> None:
    db = SessionLocal()
    try:
        summary = run_tick(db)
        if summary["pushed"]:
            logger.info("push tick: %s", summary)
    finally:
        db.close()


_task: asyncio.Task | None = None


def start() -> None:
    global _task
    if DISABLED:
        logger.info("push scheduler disabled by COGNISENSE_DISABLE_SCHEDULER")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
