"""Brute-force throttling and account-recovery codes.

LoginAttempt is the throttle's memory. It lives in the database rather than in
a process dict for two reasons: an in-memory counter resets every time the
server restarts -- which an attacker can often cause, and can certainly wait
out -- and it is not shared if the app is ever run with more than one worker.

RecoveryCode is the answer to "I forgot my password" for a system with no mail
server. See app/routes/recovery.py for why codes rather than email links.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class LoginAttempt(Base):
    """Failure counter for one throttle key, over one rolling window.

    A key is either `user:<username>` or `ip:<address>`. Both are tracked:
    per-user alone lets an attacker spray one guess across thousands of
    accounts, and per-IP alone punishes everyone behind a shared NAT for one
    bad actor. Either key tripping is enough to refuse.
    """

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), nullable=False, unique=True, index=True)

    failures = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime, nullable=False)
    last_failure_at = Column(DateTime, nullable=True)

    # Set once the threshold is crossed. Null means "not currently locked".
    locked_until = Column(DateTime, nullable=True)

    # Survives the rolling window, so repeat offenders are locked out for
    # longer each time instead of getting a clean slate every 15 minutes.
    lockout_count = Column(Integer, nullable=False, default=0)


class EmailToken(Base):
    """A single-use token delivered by email: verify an address, or reset a password.

    One table for both purposes because the machinery is identical -- random
    token, stored as a hash, short expiry, consumed on use -- and `purpose`
    keeps them from being interchangeable. A verification link must not be
    redeemable as a password reset.

    Hashed like everything else here: an attacker reading the database must not
    come away with live reset links.
    """

    __tablename__ = "email_tokens"

    PURPOSE_VERIFY = "verify"
    PURPOSE_RESET = "reset"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    token_hash = Column(String(64), nullable=False, index=True)
    purpose = Column(String(20), nullable=False, index=True)

    # The address the token was issued for. A reset token is refused if the
    # account's email has changed since -- otherwise a link mailed to an old
    # address stays live after the user moves away from it.
    email = Column(String(320), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="email_tokens")


class RecoveryCode(Base):
    """One single-use account-recovery code.

    Stored as a SHA-256 hash for the same reason session tokens are: the plain
    codes are shown to the user exactly once, at generation, and a stolen
    database must not yield a working set of them.
    """

    __tablename__ = "recovery_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="recovery_codes")
