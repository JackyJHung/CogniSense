"""User ORM model: demographics + wake/sleep times for check-in scheduling."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Time
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Demographics used for research-benchmark comparison
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)   # female | male | nonbinary | other | prefer_not
    race = Column(String, nullable=False)     # white | black | hispanic | aapi | ai_an | other | prefer_not

    # Daily schedule for check-in reminders
    wake_time = Column(Time, nullable=False)
    sleep_time = Column(Time, nullable=False)

    # Rolling aggregates (updated after each evening check-in)
    cumulative_recall_score = Column(Float, default=0.0)
    cumulative_checkin_count = Column(Integer, default=0)

    # Behavioural signal: count of times the user reopened the morning page after
    # they'd already submitted. Repeated checking is a soft anxiety/compulsion
    # marker, surfaced in the risk report as a small additive modifier.
    morning_revisit_count = Column(Integer, default=0, nullable=False)

    # Optional, and only usable for account recovery once verified. An
    # unverified address is worse than none: a typo at signup would send reset
    # links to a stranger's inbox, turning recovery into account takeover.
    email = Column(String(320), nullable=True, index=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def email_is_verified(self) -> bool:
        return bool(self.email and self.email_verified_at)

    # Minutes to ADD to UTC to reach this user's local time, so UTC-7 is -420.
    # The browser reports it when subscribing to notifications. Without it the
    # server has no way to know whether it is the middle of someone's night --
    # wake_time and sleep_time above are bare clock times with no zone.
    utc_offset_minutes = Column(Integer, default=0, nullable=False)

    # Cooldown anchor for reminder pushes, so a standing reminder cannot turn
    # into a notification every minute.
    last_push_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
