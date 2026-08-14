"""Login sessions.

WHY OPAQUE TOKENS RATHER THAN JWT
`python-jose` was in requirements.txt from the start but never imported, so the
choice was still open. Database-backed sessions win here for two reasons:

  Revocation is real. Logout currently does nothing on the server -- it clears
  localStorage and the "session" remains valid forever, because there is nothing
  to invalidate. A JWT has the same problem unless you add a blocklist, at which
  point you have a session table anyway. For an app holding cognitive-health
  data, "log me out everywhere" has to actually work.

  No signing-key lifecycle. A JWT secret must be stable across restarts or every
  token dies; that means another secret to generate, store and never commit.
  A random token compared against a hash needs none of that.

WHAT IS STORED
The SHA-256 of the token, never the token itself. Anyone who reads this table --
a leaked backup, a stray copy of cognisense.db -- gets hashes they cannot present
to the API. The raw token exists only in the response to /users/login and in the
client's storage.

A plain unsalted SHA-256 is right here and would be wrong for a password: these
tokens are 256 bits of `secrets` output, so there is no dictionary to attack and
nothing for a slow KDF to defend against.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class UserSession(Base):
    # Named UserSession, not Session -- `Session` is SQLAlchemy's own type and
    # the collision would be a permanent source of confusing imports.
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # SHA-256 hex of the bearer token. Unique so a lookup is a single index hit.
    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Shown on a "your devices" screen; also makes a stolen-session postmortem
    # possible.
    user_agent = Column(String(400), nullable=True)

    user = relationship("User", backref="sessions")
