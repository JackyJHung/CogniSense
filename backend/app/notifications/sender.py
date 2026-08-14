"""Sending a push, and cleaning up after the ones that fail.

Push endpoints rot. A user reinstalls the browser, clears site data, or the push
service rotates the endpoint, and the old one is gone forever. The service says
so with 404 or 410, and the only correct response is to delete the row -- retrying
is pure waste and the failure count will never recover.

Everything else (timeouts, 429, 500s) is treated as transient: counted, and the
subscription retired only after MAX_CONSECUTIVE_FAILURES in a row.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.models.push import MAX_CONSECUTIVE_FAILURES, PushSubscription
from app.notifications.vapid import VAPID_SUBJECT, private_key_path

logger = logging.getLogger(__name__)

# How long the push service should hold the message if the device is offline.
# Four hours: a reminder that surfaces the next morning is noise, not help.
DEFAULT_TTL_SECONDS = 4 * 60 * 60

# Statuses that mean "this subscription will never work again".
GONE_STATUSES = {404, 410}


@dataclass
class SendResult:
    ok: bool
    status: int | None = None
    gone: bool = False
    error: str | None = None


def send_to_subscription(
    subscription_info: dict, payload: dict, ttl: int = DEFAULT_TTL_SECONDS,
) -> SendResult:
    """Blocking. Call from a worker thread, never from the event loop."""
    try:
        response = webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=private_key_path(),
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=ttl,
        )
        return SendResult(ok=True, status=getattr(response, "status_code", None))
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return SendResult(
            ok=False,
            status=status,
            gone=status in GONE_STATUSES,
            error=str(exc)[:200],
        )
    except Exception as exc:  # network down, DNS failure, ...
        return SendResult(ok=False, error="{}: {}".format(type(exc).__name__, str(exc)[:180]))


def notify_user(db: Session, user_id: int, payload: dict) -> dict:
    """Push to every device this user has registered. Returns a small summary.

    Prunes dead subscriptions as a side effect, so the table does not grow a
    tail of endpoints that can never be delivered to.
    """
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not subs:
        return {"sent": 0, "failed": 0, "removed": 0, "devices": 0}

    now = datetime.now(timezone.utc)
    sent = failed = removed = 0

    for sub in subs:
        result = send_to_subscription(sub.to_info(), payload)

        if result.ok:
            sent += 1
            sub.last_success_at = now
            sub.failure_count = 0
            continue

        failed += 1
        sub.last_failure_at = now
        sub.failure_count = (sub.failure_count or 0) + 1

        if result.gone:
            logger.info("push endpoint gone (%s); removing subscription %s",
                        result.status, sub.id)
            db.delete(sub)
            removed += 1
        elif sub.failure_count >= MAX_CONSECUTIVE_FAILURES:
            logger.info("subscription %s failed %d times in a row; removing",
                        sub.id, sub.failure_count)
            db.delete(sub)
            removed += 1
        else:
            logger.warning("push failed (status=%s): %s", result.status, result.error)

    db.commit()
    return {"sent": sent, "failed": failed, "removed": removed, "devices": len(subs)}
