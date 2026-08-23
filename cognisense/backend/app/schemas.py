"""Pydantic schemas for API request/response bodies."""

from datetime import datetime, time
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# Free-text fields are user-supplied and stored verbatim; bound them so a single
# request cannot exhaust memory or the database.
MAX_TEXT_LEN = 5000
MAX_LATENCY_MS = 24 * 60 * 60 * 1000

Gender = Literal["female", "male", "nonbinary", "other", "prefer_not"]
Race = Literal["white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not"]


# ---------- User ----------

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    # bcrypt only considers the first 72 bytes, so cap the length rather than
    # silently truncating.
    password: str = Field(..., min_length=8, max_length=72)
    age: int = Field(..., ge=18, le=120)
    gender: Gender
    race: Race
    wake_time: time
    sleep_time: time


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    age: int
    gender: str
    race: str
    wake_time: time
    sleep_time: time
    created_at: datetime


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------- Morning check-in ----------

class MorningCheckinCreate(BaseModel):
    planned_activities: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)


class AssociationPresented(BaseModel):
    id: int
    object_name: str
    cue_word: str
    image_path: str


class MorningCheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    planned_activities: str
    presented_associations: list[AssociationPresented]
    disclaimer: str


# ---------- Midday check-in ----------

class MiddayCheckinCreate(BaseModel):
    morning_checkin_id: Optional[int] = Field(None, ge=1)
    what_user_has_done: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    planned_remainder: Optional[str] = Field(None, max_length=MAX_TEXT_LEN)
    response_latency_ms: Optional[int] = Field(None, ge=0, le=MAX_LATENCY_MS)


class MiddayCheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    what_user_has_done: str
    planned_remainder: Optional[str]
    disclaimer: str


# ---------- Evening check-in ----------

class AssociationResponse(BaseModel):
    association_id: int = Field(..., ge=1)
    user_answer: str = Field(..., max_length=256)
    response_latency_ms: int = Field(..., ge=0, le=MAX_LATENCY_MS)


class EveningCheckinCreate(BaseModel):
    morning_checkin_id: int = Field(..., ge=1)
    recalled_activities: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    association_responses: list[AssociationResponse] = Field(..., max_length=50)


class EveningCheckinOut(BaseModel):
    id: int
    timestamp: datetime
    activity_recall_accuracy: Optional[float]
    association_accuracy: float
    avg_response_latency_ms: Optional[int]
    daily_cognitive_score: Optional[float]
    behavioral_biomarker_score: Optional[float]
    speech_biomarker_score: Optional[float]
    disclaimer: str


# ---------- Risk comparison / report ----------

class RiskComparisonOut(BaseModel):
    user_recent_avg_score: float             # 0-1, higher = better
    peer_expected_prevalence_pct: float      # e.g. 5.0 for "5% of age-matched peers have AD"
    scd_peer_prevalence_pct: float
    elevated_concern: bool
    concern_reason: Optional[str]
    suggestions: list[str]
    citations: list[str]
    disclaimer: str


class DailySuggestionsOut(BaseModel):
    suggestions: list[str]
    lancet_risk_factor_source: str
    disclaimer: str
