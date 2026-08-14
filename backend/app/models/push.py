"""Web Push subscriptions.

One row per browser/device a user has granted notification permission on. A
person with a laptop and a phone has two rows; both get notified.

The three fields that matter come straight from the browser's
`PushSubscription` object:

  endpoint  the push service URL to POST to (Google FCM, Mozilla autopush, ...)
  p256dh    the client's public key, used to encrypt the payload
  auth      a shared secret, also used in the encryption

Nothing here is a credential for OUR server -- it is the browser's own handle,
and it is useless to anyone without the VAPID private key. It is still personal
data (it identifies a device), so `backend/db/` stays gitignored.

Endpoints expire and get rotated by the push service. A subscription that
returns 404 or 410 is dead and is deleted rather than retried; anything else is
counted in `failure_count` and retired after repeated failures.
"""

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# A subscription that has failed this many times in a row is dropped, on the
# assumption the device is gone for good.
MAX_CONSECUTIVE_FAILURES = 5


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_endpoint"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    endpoint = Column(Text, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)

    # Purely diagnostic -- helps a user recognise which device a row is.
    user_agent = Column(String, nullable=True)

    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)

    user = relationship("User", backref="push_subscriptions")

    def to_info(self) -> dict:
        """The shape pywebpush expects for `subscription_info`."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }
