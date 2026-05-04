"""Check-in ORM models: records of daily morning, midday, and evening sessions."""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MorningCheckin(Base):
    """
    Start-of-day check-in.
    - User lists activities they plan for the day (free text).
    - System presents 5 image associations they must recall in the evening.
    """
    __tablename__ = "morning_checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    planned_activities = Column(Text, nullable=False)    # free-text list
    presented_associations = Column(JSON, nullable=False) # [{image_id, object, cue_word}, ...]

    # Speech biomarker (optional voice log of plans)
    speech_biomarker_score = Column(Float, nullable=True)   # 0-1, from PyTorch speech model
    audio_file_path = Column(String, nullable=True)

    user = relationship("User", backref="morning_checkins")


class MiddayCheckin(Base):
    """
    Midday light recall prompt: list what you've done so far / what you plan next.
    """
    __tablename__ = "midday_checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    morning_checkin_id = Column(Integer, ForeignKey("morning_checkins.id"), nullable=True)

    what_user_has_done = Column(Text, nullable=False)
    planned_remainder = Column(Text, nullable=True)

    response_latency_ms = Column(Integer, nullable=True)   # How long user took to respond
    speech_biomarker_score = Column(Float, nullable=True)


class EveningCheckin(Base):
    """
    End-of-day:
    - User recalls activities they actually did.
    - User is tested on the 5 image associations from morning.
    - System computes recall accuracy + overall daily biomarker score.
    """
    __tablename__ = "evening_checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    morning_checkin_id = Column(Integer, ForeignKey("morning_checkins.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    recalled_activities = Column(Text, nullable=False)
    activity_recall_accuracy = Column(Float, nullable=True)    # 0-1

    # Image-association test results
    association_responses = Column(JSON, nullable=False)  # [{image_id, user_answer, correct}, ...]
    association_accuracy = Column(Float, nullable=False)  # 0-1

    # Average response latency across the image test, in ms
    avg_response_latency_ms = Column(Integer, nullable=True)

    # Behavioral biomarker composite score from the PyTorch model (0-1, higher=more normal)
    behavioral_biomarker_score = Column(Float, nullable=True)
    # Speech biomarker from optional evening voice note
    speech_biomarker_score = Column(Float, nullable=True)

    # Combined daily cognitive score
    daily_cognitive_score = Column(Float, nullable=True)

    user = relationship("User", backref="evening_checkins")
