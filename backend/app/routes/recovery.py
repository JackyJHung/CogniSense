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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.auth import get_current_user, revoke_all_sessions
from app.database import get_db
from app.models.security import RecoveryCode
from app.models.user import User
from app.ratelimit import check_or_raise, clear, keys_for, register_failure
from app.schemas import RecoverRequest, RecoveryCodesOut, RecoveryStatusOut, AuthOut

router = APIRouter(prefix="/recovery", tags=["recovery"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

    # Imported here to avoid a circular import at module load: users.py imports
    # from app.auth, and this module is imported by main.py alongside it.
    from app.routes.users import issue_session

    return issue_session(db, user, user_agent, response)
