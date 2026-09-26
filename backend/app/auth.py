"""Authentication: issuing sessions and proving who is calling.

THE HOLE THIS CLOSES
Every endpoint used to take `user_id` from the path or body and simply trust it.
`GET /reminders/4` returned user 4's reminders to anyone who asked. Changing a
digit in the URL read somebody else's memory scores, check-ins and risk report.
That is an IDOR, and on this data it is the whole confidentiality model.

TWO CHECKS, BOTH NECESSARY
  1. Authentication -- `get_current_user` resolves a bearer token to a user, or
     401s. Nothing else identifies the caller.
  2. Authorisation -- knowing WHO is calling does not by itself stop them asking
     for someone else's row. Routes carrying a `{user_id}` use `require_self`;
     routes carrying a resource id (a reminder, a check, a morning check-in)
     must verify that resource belongs to the caller, via `owned_or_404`.

Missing (2) is the subtler failure: a logged-in user is still a valid user, so
the request authenticates fine and returns data that is not theirs.

WHY 404 AND NOT 403 FOR RESOURCES
`owned_or_404` returns 404 for a row that exists but belongs to someone else.
403 would confirm the id is real, which leaks the existence and numbering of
other people's records. For `{user_id}` paths 403 is fine -- the caller already
knows their own id, and a clear "that isn't you" is the more useful error.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, TypeVar

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import config
from app.csrf import SESSION_COOKIE
from app.database import get_db
from app.models.session import UserSession
from app.models.user import User

# Absolute lifetime: long enough that a daily-check-in app does not nag for a
# password, short enough that an abandoned device stops working within a month.
SESSION_TTL_DAYS = config.SESSION_TTL_DAYS

# Idle lifetime. Absolute expiry alone is not enough: a session created 29 days
# ago and untouched for 28 of them is still valid, which is exactly the session
# sitting on a lost laptop. `last_used_at` was already recorded on every
# request; this is what finally reads it.
SESSION_IDLE_DAYS = config.SESSION_IDLE_DAYS

# 32 bytes -> 43 url-safe characters. Far beyond guessing.
TOKEN_BYTES = 32

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_token(raw_token: str) -> str:
    """SHA-256 hex. See the note in models/session.py on why this is enough."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User, user_agent: str | None = None) -> str:
    """Issue a session and return the RAW token -- the only time it exists."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(UserSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
        user_agent=(user_agent or None) and user_agent[:400],
    ))
    db.commit()
    return raw


def revoke_session(db: Session, raw_token: str) -> bool:
    removed = (
        db.query(UserSession)
        .filter(UserSession.token_hash == hash_token(raw_token))
        .delete(synchronize_session=False)
    )
    db.commit()
    return bool(removed)


def revoke_all_sessions(db: Session, user_id: int) -> int:
    removed = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed


def _token_from_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def session_token_from(request: Request, authorization: str | None) -> str | None:
    """Two accepted transports, checked in that order.

    The header wins so a native client (the desktop app) is unaffected by
    whatever cookies a shared browser session happens to hold. Browsers use the
    HttpOnly cookie, which script cannot read -- see app/csrf.py.
    """
    return _token_from_header(authorization) or request.cookies.get(SESSION_COOKIE)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the session token to a user, or 401.

    Expired sessions are deleted on sight rather than merely rejected, so the
    table does not accumulate dead rows for users who never log in again.
    """
    raw = session_token_from(request, authorization)
    if raw is None:
        raise UNAUTHENTICATED

    session = (
        db.query(UserSession)
        .filter(UserSession.token_hash == hash_token(raw))
        .first()
    )
    if session is None:
        raise UNAUTHENTICATED

    now = datetime.now(timezone.utc)

    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    expires = _aware(session.expires_at)
    if expires is not None and expires <= now:
        db.delete(session)
        db.commit()
        raise UNAUTHENTICATED

    # Idle expiry. Falls back to created_at for a session that has never been
    # used, so a token issued and then abandoned still ages out.
    last_seen = _aware(session.last_used_at) or _aware(session.created_at)
    if last_seen is not None and now - last_seen > timedelta(days=SESSION_IDLE_DAYS):
        db.delete(session)
        db.commit()
        raise UNAUTHENTICATED

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None:
        # The account was deleted with sessions still outstanding.
        db.delete(session)
        db.commit()
        raise UNAUTHENTICATED

    session.last_used_at = now
    db.commit()
    return user


def require_self(user_id: int, current_user: User = Depends(get_current_user)) -> User:
    """For routes with `{user_id}` in the path: it must be the caller's own id.

    FastAPI resolves `user_id` from the path parameters of whichever route
    declares this dependency, so the check happens before the handler runs.
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data",
        )
    return current_user


def require_own_id(claimed_user_id: int, current_user: User) -> User:
    """For routes taking user_id in the BODY rather than the path.

    `require_self` reads path parameters, so it cannot cover these. Clients still
    send user_id in the body, and a mismatch means either a confused client or an
    attempt to write into someone else's account -- both worth rejecting.
    """
    if claimed_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data",
        )
    return current_user


T = TypeVar("T")


def owned_or_404(resource: Optional[T], current_user: User, what: str = "Resource") -> T:
    """For routes keyed by a resource id: 404 unless it exists AND is the caller's.

    Deliberately does not distinguish "no such id" from "someone else's id" --
    see the module docstring.
    """
    if resource is None or getattr(resource, "user_id", None) != current_user.id:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return resource
