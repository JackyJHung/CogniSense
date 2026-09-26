"""User management: signup, login, logout, password change, profile.

Login is throttled before any password work happens -- see app/ratelimit.py for
why that ordering is the difference between a rate limit and a DoS amplifier.

Sessions are delivered two ways from the same code path: an HttpOnly cookie for
browsers (script cannot read it) and a bearer token in the response body for the
desktop client, which keeps no cookies. See app/csrf.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_TTL_DAYS,
    create_session,
    get_current_user,
    require_self,
    revoke_all_sessions,
    revoke_session,
    session_token_from,
)
from app.csrf import attach_session_cookies, clear_session_cookies, new_csrf_token
from app.database import get_db
from app.models.user import User
from app.ratelimit import check_or_raise, clear, keys_for, register_failure
from app.schemas import (
    AuthOut,
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    TimezoneUpdate,
    UserCreate,
    UserOut,
)
from app.timezones import adopt_if_unknown

router = APIRouter(prefix="/users", tags=["users"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Verified against when the username does not exist, so a login attempt costs
# the same either way. Without it, "no such user" returns immediately while a
# real username pays for a bcrypt round -- a timing difference big enough to
# enumerate accounts, which would undo the identical error message below.
_TIMING_EQUALISER_HASH = pwd_context.hash("cognisense-timing-equaliser")


def _password_matches(plain: str, stored_hash: str) -> bool:
    """Verify without ever raising.

    passlib raises UnknownHashError when `stored_hash` is not a recognised
    bcrypt digest -- a corrupted row, a half-finished migration, a hand-edited
    database. Letting that propagate turns a failed login into a 500, which
    crashes the request AND distinguishes "this account exists but its hash is
    broken" from an ordinary wrong password.
    """
    try:
        return pwd_context.verify(plain, stored_hash)
    except Exception:
        return False


def issue_session(db: Session, user: User, user_agent: str | None, response: Response) -> AuthOut:
    """Mint a session and deliver it by cookie AND body token."""
    token = create_session(db, user, user_agent)
    attach_session_cookies(response, token, new_csrf_token())
    return AuthOut(
        user=UserOut.model_validate(user),
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
    )


@router.post("/signup", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def signup(
    payload: UserCreate,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    # Throttled too: signup runs bcrypt, so it is the same DoS surface as login.
    keys = keys_for(None, request)
    check_or_raise(db, keys)

    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        register_failure(db, keys)
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=payload.username,
        hashed_password=pwd_context.hash(payload.password),
        age=payload.age,
        gender=payload.gender,
        race=payload.race,
        wake_time=payload.wake_time,
        sleep_time=payload.sleep_time,
        timezone=payload.timezone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return issue_session(db, user, user_agent, response)


@router.post("/login", response_model=AuthOut)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    keys = keys_for(payload.username, request)

    # FIRST. Before the user lookup, before bcrypt. A locked-out caller must
    # cost one indexed SELECT, not 250ms of hashing -- otherwise the throttle
    # is itself the denial of service.
    check_or_raise(db, keys)

    user = db.query(User).filter(User.username == payload.username).first()

    stored = user.hashed_password if user else _TIMING_EQUALISER_HASH
    password_ok = _password_matches(payload.password, stored)

    # One message and one code for both "no such user" and "wrong password", so
    # the endpoint cannot be used to enumerate which usernames exist.
    if not user or not password_ok:
        register_failure(db, keys)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear(db, keys)
    # Accounts from before zones existed learn theirs at the next login.
    if adopt_if_unknown(user, payload.timezone):
        db.commit()
    return issue_session(db, user, user_agent, response)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = None,
    authorization: Optional[str] = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actually end the session server-side, and drop the cookies."""
    clear_session_cookies(response)

    if payload is not None and payload.all_devices:
        return {"revoked": revoke_all_sessions(db, current_user.id), "scope": "all"}

    raw = session_token_from(request, authorization)
    revoked = revoke_session(db, raw) if raw else False
    return {"revoked": int(revoked), "scope": "current"}


@router.post("/password", response_model=AuthOut)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_agent: Optional[str] = Header(default=None),
):
    """Change the password, then re-issue a single fresh session.

    Throttled on the current password: this endpoint verifies a password, so
    without a limit it is another guessing oracle -- and one reachable with a
    stolen session that does not yet know the password.

    EVERY existing session is revoked, including this one, and a new session is
    issued in the response. That is the point of changing a password after a
    suspected compromise: an attacker holding a stolen token must lose it. The
    caller stays logged in on this device only.
    """
    # Its own scope: a failed password change must not lock the user out of
    # logging in, nor vice versa.
    keys = keys_for(current_user.username, request, scope="pwchange")
    check_or_raise(db, keys)

    if not _password_matches(payload.current_password, current_user.hashed_password):
        register_failure(db, keys)
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    current_user.hashed_password = pwd_context.hash(payload.new_password)
    db.commit()

    revoke_all_sessions(db, current_user.id)
    clear(db, keys)
    return issue_session(db, current_user, user_agent, response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Who is this session? Lets a client validate stored state on startup."""
    return current_user


@router.post("/me/timezone", response_model=UserOut)
def set_timezone(
    payload: TimezoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set the zone the user's days are counted in -- a deliberate choice.

    Unlike login, this overwrites: it is the user saying where they live, and
    the only thing that changes a zone once an account has one. An unknown
    name is a 422 (TimezoneUpdate), never a silent UTC.
    """
    current_user.timezone = payload.timezone
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, current_user: User = Depends(require_self)):
    """Only ever your own profile -- require_self rejects anyone else's id."""
    return current_user
