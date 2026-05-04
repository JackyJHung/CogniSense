"""Pydantic schemas for API request/response bodies."""

from datetime import datetime, time
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


Gender = Literal["female", "male", "nonbinary", "other", "prefer_not"]
Race = Literal["white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not"]


# ---------- User ----------

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)
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
    username: str
    password: str


# ---------- Morning check-in ----------

class MorningCheckinCreate(BaseModel):
    user_id: int
    planned_activities: str


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
    user_id: int
    morning_checkin_id: Optional[int] = None
    what_user_has_done: str
    planned_remainder: Optional[str] = None
    response_latency_ms: Optional[int] = None


class MiddayCheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    what_user_has_done: str
    planned_remainder: Optional[str]
    disclaimer: str


# ---------- Evening check-in ----------

class AssociationResponse(BaseModel):
    association_id: int
    user_answer: str
    response_latency_ms: int


class EveningCheckinCreate(BaseModel):
    user_id: int
    morning_checkin_id: int
    recalled_activities: str
    association_responses: list[AssociationResponse]


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
