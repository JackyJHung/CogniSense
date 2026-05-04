"""User ORM model: demographics + wake/sleep times for check-in scheduling."""

from sqlalchemy import Column, Integer, String, Time, DateTime, Float
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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
