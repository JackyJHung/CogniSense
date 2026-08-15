"""Brute-force throttling for credential endpoints.

WHY THE ORDER OF OPERATIONS IS THE WHOLE POINT
bcrypt is deliberately slow -- roughly 250ms of pinned CPU per verification.
That is exactly what makes it good at resisting offline cracking, and exactly
what makes an unthrottled login endpoint a denial-of-service amplifier: a few
concurrent attackers sending garbage can saturate the CPU and take the API down
without ever guessing anything.

Adding the timing-equaliser hash (so unknown usernames cost the same as real
ones, and cannot be enumerated by response time) made this *worse*, because now
every junk request pays the bcrypt cost too.

So the throttle check must happen BEFORE any password verification, and it must
be cheap: one indexed lookup on a short key. `check_or_raise` is called at the
top of the login handler, ahead of the user query and the hash comparison.

TWO KEYS, BOTH ENFORCED
  user:<username>   stops one account being ground down by guesses
  ip:<address>      stops one host spraying a single guess across many accounts

Per-user alone misses the spray attack. Per-IP alone punishes a whole household
or office behind one NAT for a single bad actor, so its threshold is looser.
Either key tripping is enough to refuse.

ESCALATION
`lockout_count` outlives the rolling window, so repeat offenders wait longer
each time (1m, 2m, 4m ... capped at 1h) rather than getting a clean slate every
fifteen minutes and resuming at full speed.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app import config
from app.models.security import LoginAttempt

logger = logging.getLogger(__name__)

# Rolling window in which failures accumulate.
WINDOW_MINUTES = 15

# Failures allowed inside the window before the key locks.
USER_MAX_FAILURES = 5
IP_MAX_FAILURES = 20

BASE_LOCKOUT_SECONDS = 60
MAX_LOCKOUT_SECONDS = 60 * 60

# Rows are pruned on roughly this fraction of failures, so an attacker rotating
# through addresses cannot grow the table without bound, and a normal request
# almost never pays for the delete.
PRUNE_PROBABILITY = 0.02


def _now() -> datetime:
    """Naive UTC, matching every other timestamp comparison in this codebase."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class ThrottleDecision:
    allowed: bool
    retry_after: int = 0
    key: str | None = None


def client_ip(request: Request | None) -> str:
    """The caller's address, believing X-Forwarded-For only from a trusted peer.

    THE BUG THIS FIXES. This used to trust X-Forwarded-For whenever the header
    was present. Since any client can set an arbitrary header, an attacker had
    only to send a different `X-Forwarded-For` value on each request to get a
    fresh per-IP budget every time -- which defeats the per-IP limit completely,
    silently, and precisely when it matters. The per-user limit still applied,
    but the address limit (the one that stops a single host spraying one guess
    across many accounts) was decorative.

    Now the header is read only when the DIRECT peer is a configured trusted
    proxy. With no proxies configured -- the default -- the socket address is
    always used and the header is ignored entirely.

    Note the proxy must also strip inbound X-Forwarded-For, otherwise a client
    can prepend a forged entry that the proxy then appends to.
    """
    if request is None:
        return "unknown"

    peer = (request.client.host if request.client else "unknown")

    if peer in config.TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Leftmost entry is the original client, as appended by each hop.
            return forwarded.split(",")[0].strip()[:100]

    return peer[:100]


def keys_for(
    username: str | None, request: Request | None, scope: str = "login",
) -> list[str]:
    """Throttle keys, namespaced by `scope`.

    WHY THE SCOPE EXISTS. Login and account recovery must have SEPARATE budgets.
    Sharing them looks tidier and is actively harmful: someone who has forgotten
    their password will fail login several times, trip the lockout, and then
    reach for recovery -- and find recovery locked too. The one path back into
    the account is barred at precisely the moment it is needed, by their own
    honest attempts.

    Separate namespaces keep both protected without that trap. Guessing a
    recovery code is hopeless regardless: they carry ~100 bits of entropy, so
    the limit there is about server load rather than guessability.
    """
    keys = ["{}:ip:{}".format(scope, client_ip(request))]
    if username:
        keys.append("{}:user:{}".format(scope, username.strip().lower()[:150]))
    return keys


def _limit_for(key: str) -> int:
    # Keys are "<scope>:user:<name>" or "<scope>:ip:<addr>".
    return USER_MAX_FAILURES if ":user:" in key else IP_MAX_FAILURES


def _lockout_seconds(lockout_count: int) -> int:
    return min(BASE_LOCKOUT_SECONDS * (2 ** max(0, lockout_count)), MAX_LOCKOUT_SECONDS)


def check(db: Session, keys: list[str]) -> ThrottleDecision:
    """Cheap pre-flight. No password work happens if this refuses."""
    now = _now()
    for key in keys:
        row = db.query(LoginAttempt).filter(LoginAttempt.key == key).first()
        if row is None or row.locked_until is None:
            continue
        if row.locked_until > now:
            return ThrottleDecision(
                allowed=False,
                retry_after=max(1, int((row.locked_until - now).total_seconds())),
                key=key,
            )
    return ThrottleDecision(allowed=True)


def check_or_raise(db: Session, keys: list[str]) -> None:
    """429 with Retry-After when locked. Call before touching bcrypt."""
    decision = check(db, keys)
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            "Too many failed attempts. Try again in "
            f"{decision.retry_after} seconds."
        ),
        headers={"Retry-After": str(decision.retry_after)},
    )


def register_failure(db: Session, keys: list[str]) -> None:
    """Count one failure against every key, locking any that cross its limit."""
    now = _now()
    window_start = now - timedelta(minutes=WINDOW_MINUTES)

    for key in keys:
        row = db.query(LoginAttempt).filter(LoginAttempt.key == key).first()
        if row is None:
            row = LoginAttempt(key=key, failures=0, window_started_at=now)
            db.add(row)

        # Outside the window: start counting again, but keep lockout_count so
        # escalation survives.
        if row.window_started_at < window_start:
            row.window_started_at = now
            row.failures = 0

        row.failures += 1
        row.last_failure_at = now

        if row.failures >= _limit_for(key):
            seconds = _lockout_seconds(row.lockout_count)
            row.locked_until = now + timedelta(seconds=seconds)
            row.lockout_count += 1
            row.failures = 0
            row.window_started_at = now
            logger.warning("throttle: %s locked for %ss", key, seconds)

    db.commit()

    if random.random() < PRUNE_PROBABILITY:
        prune(db)


def clear(db: Session, keys: list[str]) -> None:
    """Called on a successful login.

    Only the user key is reset. The IP key deliberately survives: one success
    among a flood of failures is what a successful credential-stuffing run looks
    like, and clearing the address counter on it would hand the attacker a reset.
    """
    for key in keys:
        if ":user:" not in key:
            continue
        db.query(LoginAttempt).filter(LoginAttempt.key == key).delete(
            synchronize_session=False
        )
    db.commit()


def prune(db: Session, older_than_minutes: int = 24 * 60) -> int:
    """Drop stale rows that are neither locked nor recently active."""
    cutoff = _now() - timedelta(minutes=older_than_minutes)
    removed = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.window_started_at < cutoff)
        .filter(
            (LoginAttempt.locked_until.is_(None)) | (LoginAttempt.locked_until < _now())
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed
