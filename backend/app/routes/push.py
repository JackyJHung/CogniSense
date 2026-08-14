"""Web Push subscription management.

The browser does the hard part: it asks the user for permission, talks to its
own push service, and hands back an endpoint plus two keys. All this module does
is store that, hand out the VAPID public key, and offer a "send me one now"
button so a user can confirm the whole chain works before relying on it.

That test endpoint matters more than it looks. Push has many moving parts --
permission, service worker registration, VAPID keys, the push service, OS-level
notification settings -- and when it silently does nothing there is no way to
tell which link is broken. Being able to press a button and see a notification
turns a black box into something diagnosable.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_self
from app.database import get_db
from app.models.push import PushSubscription
from app.models.user import User
from app.notifications import scheduler
from app.notifications.sender import notify_user
from app.notifications.vapid import public_key_b64
from app.schemas import (
    PushSendResultOut,
    PushStatusOut,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key")
def vapid_public_key():
    """The applicationServerKey the browser subscribes with.

    Deliberately unauthenticated: this is a PUBLIC key, it is identical for
    every user, and the browser needs it before a subscription exists. Nothing
    is learned by fetching it.

    Generated on first call and then stable forever -- rotating it would
    invalidate every existing subscription.
    """
    return {"public_key": public_key_b64()}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: PushSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a device. Idempotent on the endpoint.

    Re-subscribing with the same endpoint updates the keys in place rather than
    creating a duplicate: browsers hand back the same endpoint on every call
    once permission is granted, so a naive insert would violate the unique
    constraint on every page load.
    """
    if payload.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data",
        )
    user = current_user

    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == payload.subscription.endpoint)
        .first()
    )
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = payload.subscription.keys.p256dh
        existing.auth = payload.subscription.keys.auth
        existing.user_agent = payload.user_agent
        existing.failure_count = 0
        sub = existing
    else:
        sub = PushSubscription(
            user_id=user.id,
            endpoint=payload.subscription.endpoint,
            p256dh=payload.subscription.keys.p256dh,
            auth=payload.subscription.keys.auth,
            user_agent=payload.user_agent,
        )
        db.add(sub)

    # The browser is the only party that knows the device's real offset, and
    # the scheduler needs it to avoid pushing in the middle of the night.
    user.utc_offset_minutes = payload.utc_offset_minutes

    db.commit()
    db.refresh(sub)
    return {"id": sub.id, "endpoint": sub.endpoint, "devices": len(user.push_subscriptions)}


@router.post("/unsubscribe")
def unsubscribe(
    payload: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forget a device. Returns 200 whether or not it was registered.

    Scoped to the caller's own rows. Without the user_id filter, knowing an
    endpoint string was enough to silently switch off someone else's reminder
    notifications -- a quiet denial of service against a memory aid, which is
    the one kind of failure the person using it would be least likely to notice.
    """
    removed = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == current_user.id)
        .filter(PushSubscription.endpoint == payload.endpoint)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"removed": removed}


@router.get("/status/{user_id}", response_model=PushStatusOut)
def push_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    user = current_user
    devices = (
        db.query(PushSubscription).filter(PushSubscription.user_id == user_id).count()
    )
    wake = user.wake_time.strftime("%H:%M") if user.wake_time else "?"
    sleep = user.sleep_time.strftime("%H:%M") if user.sleep_time else "?"
    return PushStatusOut(
        enabled=devices > 0,
        devices=devices,
        last_push_at=user.last_push_at,
        cooldown_hours=scheduler.COOLDOWN_HOURS,
        quiet_hours=f"quiet between {sleep} and {wake} local",
        currently_awake=scheduler.is_awake(user),
        scheduler_running=not scheduler.DISABLED,
    )


@router.post("/test/{user_id}", response_model=PushSendResultOut)
def send_test(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self),
):
    """Push immediately, ignoring cooldown and quiet hours.

    Deliberately bypasses both: this is the user pressing a button and expecting
    something to happen. It does NOT update last_push_at, so testing cannot
    suppress the next real reminder.
    """
    result = notify_user(db, user_id, {
        "title": "CogniSense notifications are working",
        "body": "This is a test. Real reminders will look like this.",
        "tag": "cognisense-test",
        "url": "/reminders",
    })
    if result["devices"] == 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "no_devices",
                "message": "No device is registered for notifications yet.",
            },
        )
    detail = None
    if result["sent"] == 0:
        detail = (
            "Every registered device rejected the push. If this device was "
            "re-installed or site data was cleared, turn notifications off and "
            "on again to re-register it."
        )
    return PushSendResultOut(**result, detail=detail)
