"""User-management endpoints: signup, login, logout, profile lookup.

Signup and login now issue a session token. Everything else in the API requires
that token; see app/auth.py for what it replaced and why.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_TTL_DAYS,
    create_session,
    get_current_user,
    require_self,
    revoke_all_sessions,
    revoke_session,
)
from app.database import get_db
from app.models.user import User
from app.schemas import AuthOut, LoginRequest, LogoutRequest, UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Verified against when the username does not exist, so that a login attempt
# costs the same either way. Without it, "no such user" returns immediately
# while a real username pays for a bcrypt round -- a timing difference big
# enough to enumerate accounts over the network, which undoes the point of
# returning an identical error message for both cases.
_TIMING_EQUALISER_HASH = pwd_context.hash("cognisense-timing-equaliser")


def _password_matches(plain: str, stored_hash: str) -> bool:
    """Verify without ever raising.

    passlib raises UnknownHashError when `stored_hash` is not a recognised
    bcrypt digest -- a corrupted row, a half-finished migration, a hand-edited
    database. Letting that propagate turns a failed login into a 500, which
    crashes the request AND distinguishes "this account exists but its hash is
    broken" from an ordinary wrong password. Refusing the login is the correct
    answer in every one of those cases.
    """
    try:
        return pwd_context.verify(plain, stored_hash)
    except Exception:
        return False


def _auth_response(db: Session, user: User, user_agent: str | None) -> AuthOut:
    token = create_session(db, user, user_agent)
    return AuthOut(
        user=UserOut.model_validate(user),
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
    )


@router.post("/signup", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def signup(
    payload: UserCreate,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=payload.username,
        hashed_password=pwd_context.hash(payload.password),
        age=payload.age,
        gender=payload.gender,
        race=payload.race,
        wake_time=payload.wake_time,
        sleep_time=payload.sleep_time,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(db, user, user_agent)


@router.post("/login", response_model=AuthOut)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    user = db.query(User).filter(User.username == payload.username).first()

    # Always run a verification, even for an unknown username, so the two paths
    # take the same time. See _TIMING_EQUALISER_HASH.
    stored = user.hashed_password if user else _TIMING_EQUALISER_HASH
    password_ok = _password_matches(payload.password, stored)

    # One message and one code for both "no such user" and "wrong password", so
    # the endpoint cannot be used to enumerate which usernames exist.
    if not user or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return _auth_response(db, user, user_agent)


@router.post("/logout")
def logout(
    payload: LogoutRequest | None = None,
    authorization: Optional[str] = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actually end the session server-side.

    Logging out used to be purely client-side: the browser dropped its copy and
    the credential stayed valid indefinitely. Now the row is deleted, so a token
    captured beforehand stops working.
    """
    if payload is not None and payload.all_devices:
        return {"revoked": revoke_all_sessions(db, current_user.id), "scope": "all"}

    raw = (authorization or "").partition(" ")[2].strip()
    return {"revoked": int(revoke_session(db, raw)), "scope": "current"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Who is this token? Lets a client validate a stored token on startup."""
    return current_user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, current_user: User = Depends(require_self)):
    """Only ever your own profile -- require_self rejects anyone else's id."""
    return current_user
