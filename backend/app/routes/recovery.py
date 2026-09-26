"""Account recovery via single-use codes.

WHY CODES AND NOT AN EMAIL RESET LINK
The usual flow -- "we've sent you a link" -- needs a mail server, a deliverable
sender domain, and handling for bounces and spam filtering. This project has
none of those, and the User model does not even store an email address. Building
a reset endpoint that pretends to send mail would be worse than useless: it
would look like a working recovery path right up to the moment somebody actually
needed it.

Recovery codes need no infrastructure, work offline, and are testable. The
trade is that the user has to keep them somewhere, which is exactly the same
trade as a bank's one-time code sheet.

If email is added later, the shape here does not change: a reset becomes
"prove you control the address" instead of "prove you hold a code", and
`_consume_and_reset` is reused unchanged.

WHAT IS STORED
SHA-256 of each code, never the code. The plaintext exists once, in the response
to a generate call. A stolen database yields nothing usable, and CogniSense
itself cannot tell a user what their codes were -- only issue new ones.

SECURITY PROPERTIES
  - single use: a code is consumed on success and cannot be replayed
  - generating a new set invalidates every unused old code
  - a successful reset revokes every existing session, so an attacker holding a
    stolen token loses it at the moment the real owner recovers the account
  - the reset endpoint is throttled on both username and IP, because it is a
    credential-guessing surface like login
  - failure is deliberately vague: "invalid username or code", so the endpoint
    cannot be used to discover which usernames exist
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import config
from app.auth import get_current_user, revoke_all_sessions
from app.database import get_db
from app.emailer import send_password_reset, send_verification
from app.models.security import EmailToken, RecoveryCode
from app.models.user import User
from app.ratelimit import check_or_raise, clear, keys_for, register_failure
from app.schemas import (
    AuthOut,
    EmailTokenRequest,
    ForgotPasswordRequest,
    GenericMessageOut,
    RecoverRequest,
    RecoveryCodesOut,
    RecoveryStatusOut,
    ResetWithTokenRequest,
    SetEmailRequest,
)
# users.py does not import this module, so there is no cycle -- these can be
# ordinary module-level imports, and password hashing stays defined in exactly
# one place rather than being configured twice with two chances to diverge.
from app.routes.users import _password_matches, issue_session, pwd_context

router = APIRouter(prefix="/recovery", tags=["recovery"])

CODE_COUNT = 10
# 4 groups of 5 chars from a 32-symbol alphabet ~= 100 bits. Far beyond guessing,
# and still short enough to write on paper.
CODE_GROUPS = 4
CODE_GROUP_LEN = 5
# No 0/O/1/I/L: these get copied off a screen by hand, often by someone who is
# worried about their memory. Ambiguous glyphs are a real failure mode here.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

WARNING = (
    "Save these somewhere safe and offline -- a note in your wallet, or with "
    "someone you trust. Each code works once. They are the only way back into "
    "the account if the password is forgotten, and CogniSense cannot show them "
    "to you again."
)


def _hash_code(code: str) -> str:
    return hashlib.sha256(_normalise(code).encode("utf-8")).hexdigest()


def _normalise(code: str) -> str:
    """Compare case- and separator-insensitively; people retype these by hand."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _generate_code() -> str:
    groups = [
        "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP_LEN))
        for _ in range(CODE_GROUPS)
    ]
    return "-".join(groups)


# ==========================================================================
# Email-delivered tokens
# ==========================================================================

def _issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    """Mint a single-use token, invalidating any outstanding one of the same kind.

    Superseding the previous token matters: a user who clicks "email me a link"
    three times should end up with one live link, not three, and the two they
    abandoned should stop working immediately.
    """
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id,
        EmailToken.purpose == purpose,
        EmailToken.used_at.is_(None),
    ).delete(synchronize_session=False)

    raw = secrets.token_urlsafe(32)
    db.add(EmailToken(
        user_id=user.id,
        token_hash=_hash_code(raw),
        purpose=purpose,
        email=user.email or "",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + ttl,
    ))
    db.commit()
    return raw


def _consume_token(db: Session, raw: str, purpose: str) -> User | None:
    """Validate and burn a token. None for anything wrong, without saying which."""
    row = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == _hash_code(raw))
        .filter(EmailToken.purpose == purpose)
        .filter(EmailToken.used_at.is_(None))
        .first()
    )
    if row is None:
        return None

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if row.expires_at <= now_naive:
        db.delete(row)
        db.commit()
        return None

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        return None

    # The address must still be the one the token was issued for. Otherwise a
    # link mailed to an old address stays live after the user moves away from
    # it -- which is exactly what someone does after losing control of an inbox.
    if (row.email or "") != (user.email or ""):
        db.delete(row)
        db.commit()
        return None

    row.used_at = datetime.now(timezone.utc)
    db.commit()
    return user


@router.post("/email", response_model=GenericMessageOut)
def set_email(
    payload: SetEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach a recovery address and send a confirmation link.

    Requires the password: a borrowed session must not be able to point recovery
    at somebody else's inbox, which would convert temporary access into
    permanent ownership of the account.
    """
    keys = keys_for(current_user.username, request, scope="setemail")
    check_or_raise(db, keys)

    if not _password_matches(payload.current_password, current_user.hashed_password):
        register_failure(db, keys)
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    address = payload.email.strip().lower()

    taken = (
        db.query(User)
        .filter(User.email == address)
        .filter(User.id != current_user.id)
        .first()
    )
    if taken is not None:
        # Generic on purpose: confirming which addresses are registered would
        # leak the membership of a cognitive-health app.
        raise HTTPException(
            status_code=409,
            detail="That address cannot be used for this account.",
        )

    current_user.email = address
    current_user.email_verified_at = None   # re-verify on every change
    db.commit()
    clear(db, keys)

    token = _issue_token(
        db, current_user, EmailToken.PURPOSE_VERIFY,
        timedelta(hours=config.VERIFY_TOKEN_HOURS),
    )
    send_verification(address, current_user.username, token)

    return GenericMessageOut(message=(
        f"Check {address} for a link to confirm the address. "
        f"It expires in {config.VERIFY_TOKEN_HOURS} hours."
    ))


@router.post("/email/verify", response_model=GenericMessageOut)
def verify_email(payload: EmailTokenRequest, db: Session = Depends(get_db)):
    """Confirm an address. The link itself is the proof, so no session needed."""
    user = _consume_token(db, payload.token, EmailToken.PURPOSE_VERIFY)
    if user is None:
        raise HTTPException(
            status_code=400,
            detail="That confirmation link is invalid or has expired. "
                   "Request a new one from Settings.",
        )
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    return GenericMessageOut(message="Email confirmed. It can now be used to reset your password.")


@router.post("/forgot", response_model=GenericMessageOut)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Email a reset link, if the account exists and has a verified address.

    ALWAYS returns the same message. Whether the account exists, whether it has
    an email, whether that email is verified -- none of it is observable. On a
    cognitive-health app, confirming that a given address has an account is
    itself a disclosure worth avoiding.
    """
    keys = keys_for(payload.identifier, request, scope="forgot")
    check_or_raise(db, keys)

    identifier = payload.identifier.strip().lower()
    user = (
        db.query(User)
        .filter((User.username == payload.identifier.strip()) | (User.email == identifier))
        .first()
    )

    if user is not None and user.email_is_verified:
        token = _issue_token(
            db, user, EmailToken.PURPOSE_RESET,
            timedelta(minutes=config.RESET_TOKEN_MINUTES),
        )
        send_password_reset(user.email, user.username, token)
    else:
        # Count it: otherwise this endpoint is a free, unlimited probe for which
        # usernames and addresses exist.
        register_failure(db, keys)

    return GenericMessageOut(message=(
        "If that account exists and has a confirmed email address, a reset link "
        "is on its way. Check your inbox, and your spam folder."
    ))


@router.post("/reset-token", response_model=AuthOut)
def reset_with_token(
    payload: ResetWithTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    """Set a new password from an emailed link."""
    keys = keys_for(None, request, scope="resettoken")
    check_or_raise(db, keys)

    user = _consume_token(db, payload.token, EmailToken.PURPOSE_RESET)
    if user is None:
        register_failure(db, keys)
        raise HTTPException(
            status_code=400,
            detail="That reset link is invalid or has expired. Request a new one.",
        )

    user.hashed_password = pwd_context.hash(payload.new_password)
    db.commit()
    revoke_all_sessions(db, user.id)
    clear(db, keys)

    return issue_session(db, user, user_agent, response)


# ==========================================================================
# Offline recovery codes
# ==========================================================================

@router.post("/codes", response_model=RecoveryCodesOut)
def generate_codes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a fresh set, invalidating any unused codes from before.

    Regenerating is how a user recovers from "I think somebody saw my codes",
    so the old set must die even though some of it is unused.
    """
    db.query(RecoveryCode).filter(
        RecoveryCode.user_id == current_user.id,
        RecoveryCode.used_at.is_(None),
    ).delete(synchronize_session=False)

    plain = [_generate_code() for _ in range(CODE_COUNT)]
    for code in plain:
        db.add(RecoveryCode(user_id=current_user.id, code_hash=_hash_code(code)))
    db.commit()

    # The only time these exist in clear anywhere.
    return RecoveryCodesOut(codes=plain, generated=len(plain), warning=WARNING)


@router.get("/status", response_model=RecoveryStatusOut)
def status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(RecoveryCode).filter(RecoveryCode.user_id == current_user.id).all()
    remaining = sum(1 for r in rows if r.used_at is None)
    return RecoveryStatusOut(
        codes_remaining=remaining,
        codes_used=sum(1 for r in rows if r.used_at is not None),
        has_codes=bool(rows),
        email=current_user.email,
        email_verified=current_user.email_is_verified,
        # Surfaced so the UI can say "this server is not sending mail" rather
        # than telling somebody to check an inbox that will stay empty.
        email_delivery_enabled=config.EMAIL_ENABLED,
    )


@router.post("/reset", response_model=AuthOut)
def reset_with_code(
    payload: RecoverRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(default=None),
):
    """Set a new password using a recovery code. No session required."""
    # scope="recovery" so this has its own budget. Sharing the login namespace
    # would lock the recovery path for anyone who had just failed to remember
    # their password -- barring the only way back in at exactly the wrong moment.
    keys = keys_for(payload.username, request, scope="recovery")
    check_or_raise(db, keys)

    user = db.query(User).filter(User.username == payload.username).first()

    row = None
    if user is not None:
        row = (
            db.query(RecoveryCode)
            .filter(RecoveryCode.user_id == user.id)
            .filter(RecoveryCode.code_hash == _hash_code(payload.code))
            .filter(RecoveryCode.used_at.is_(None))
            .first()
        )

    if user is None or row is None:
        register_failure(db, keys)
        # One message for every failure mode: unknown user, wrong code, already
        # used code. Anything more specific is an oracle.
        raise HTTPException(status_code=401, detail="Invalid username or recovery code")

    row.used_at = datetime.now(timezone.utc)
    user.hashed_password = pwd_context.hash(payload.new_password)
    db.commit()

    # Whoever held a session before this moment loses it -- the whole point of
    # recovering an account you believe someone else has reached.
    revoke_all_sessions(db, user.id)
    clear(db, keys)

    return issue_session(db, user, user_agent, response)
