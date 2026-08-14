"""Prospective-memory ORM models: things the user intends to do, and the checks.

Prospective memory -- remembering to carry out an intention at the right later
moment -- is a different faculty from the retrospective recall the evening
image-association test measures, and it tends to show change earlier. It is also
the faculty people actually notice slipping: missed appointments, unposted
letters, the pan left on the hob.

Two tables:

  ReminderItem   one thing the user said they intend to do, as free text and/or
                 an uploaded image. Owned by the user, never auto-deleted.

  ReminderCheck  one test event. Records what the user freely recalled before
                 being shown anything, which of their items that recall matched,
                 and what they reported having actually done.

The distinction between "recalled" and "done" is deliberate and is the point of
the feature: forgetting that you meant to do something is a different signal
from remembering and not getting to it.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# Lifecycle of an intention.
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_DISMISSED = "dismissed"


class ReminderItem(Base):
    """Something the user wants to do, entered as text and/or an image."""

    __tablename__ = "reminder_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # At least one of these is required; enforced at the schema layer so the
    # error reaches the client as a 422 rather than an IntegrityError.
    description = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)

    # A short label the user gives an image-only item, so there is something to
    # match a spoken/typed recall against.
    label = Column(String, nullable=True)

    # When to test them on it. Null means "include in any check".
    due_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String, nullable=False, default=STATUS_PENDING, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="reminder_items")

    @property
    def match_text(self) -> str:
        """The text a recall attempt is compared against."""
        return " ".join(p for p in (self.label, self.description) if p)


class ReminderCheck(Base):
    """One prospective-memory test: 'what did you mean to do today?'"""

    __tablename__ = "reminder_checks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    responded_at = Column(DateTime(timezone=True), nullable=True)

    # Snapshot of what was outstanding when the check fired, so the score stays
    # interpretable even after the items are completed or dismissed later.
    active_item_ids = Column(JSON, nullable=False, default=list)
    n_items_active = Column(Integer, nullable=False, default=0)

    # Free recall, captured BEFORE the user is shown anything.
    recall_text = Column(Text, nullable=True)
    matched_item_ids = Column(JSON, nullable=True)
    n_recalled = Column(Integer, nullable=True)

    # The gate: did they name at least one outstanding item unprompted?
    passed = Column(Boolean, nullable=True)

    # Whether the list was revealed. It always is, after the attempt -- this
    # records that the aid fired, not whether it was granted.
    aid_shown = Column(Boolean, nullable=False, default=False)

    # What they said they had actually completed.
    reported_done_item_ids = Column(JSON, nullable=True)
    n_reported_done = Column(Integer, nullable=True)

    # Fraction of outstanding items recalled unprompted, 0..1.
    prospective_score = Column(Float, nullable=True)

    response_latency_ms = Column(Integer, nullable=True)

    user = relationship("User", backref="reminder_checks")
