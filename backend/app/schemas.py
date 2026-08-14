"""Pydantic schemas for API request/response bodies."""

from datetime import datetime, time
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    # 95% bootstrap interval on the recent average. None when there are too few
    # scored days to estimate one -- clients must render that as "not enough
    # data yet", never as a narrow interval.
    user_recent_avg_ci_low: Optional[float] = None
    user_recent_avg_ci_high: Optional[float] = None

    # Change vs. the user's own earlier baseline, in percent, with its interval.
    # The attention warning requires this interval to exclude zero.
    trajectory_change_pct: Optional[float] = None
    trajectory_change_ci_low_pct: Optional[float] = None
    trajectory_change_ci_high_pct: Optional[float] = None
    n_scored_days: int = 0

    peer_expected_prevalence_pct: float      # e.g. 5.0 for "5% of age-matched peers have AD"
    scd_peer_prevalence_pct: float
    # Synthetic behavioural-signal modifier added on top of peer prevalence (not from research).
    # Currently driven by repeated revisits to the locked morning check-in.
    behavioral_risk_modifier_pct: float = 0.0
    behavioral_risk_modifier_reason: Optional[str] = None
    elevated_concern: bool
    concern_reason: Optional[str]

    # Distinct from "no concern": the data cannot yet separate a real decline
    # from normal day-to-day variation. Clients should show this rather than
    # implying an all-clear.
    inconclusive: bool = False
    inconclusive_reason: Optional[str] = None

    suggestions: list[str]
    citations: list[str]
    disclaimer: str


class DailySuggestionsOut(BaseModel):
    suggestions: list[str]
    lancet_risk_factor_source: str
    disclaimer: str


# ---------- Reminders / prospective memory ----------

class ReminderItemCreate(BaseModel):
    user_id: int
    description: Optional[str] = Field(None, max_length=2000)
    # Short handle for an image-only item, so a spoken recall has something to
    # match against. An image with no words attached cannot be graded.
    label: Optional[str] = Field(None, max_length=200)
    due_at: Optional[datetime] = None

    @model_validator(mode="after")
    def require_text_or_label(self):
        if not (self.description or "").strip() and not (self.label or "").strip():
            raise ValueError(
                "give the reminder a description or a short label -- an item "
                "with no words cannot be matched against what you recall"
            )
        return self


class ReminderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: Optional[str]
    label: Optional[str]
    image_path: Optional[str]
    due_at: Optional[datetime]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]


class ReminderCheckOut(BaseModel):
    """The prompt. Deliberately carries NO item text -- that is the whole test."""

    check_id: int
    triggered_at: datetime
    n_items_active: int
    prompt: str
    disclaimer: str


class ReminderRecallSubmit(BaseModel):
    recall_text: str = Field(..., max_length=4000)
    response_latency_ms: Optional[int] = None


class ItemMatchOut(BaseModel):
    item_id: int
    overlap: float
    matched: bool


class ReminderRecallResultOut(BaseModel):
    check_id: int
    n_active: int
    n_recalled: int
    passed: bool
    prospective_score: float
    feedback: str
    matches: list[ItemMatchOut]
    # The aid. Always populated after an attempt, pass or fail.
    items: list[ReminderItemOut]
    disclaimer: str
    memory_aid_disclaimer: str


class ReminderDoneUpdate(BaseModel):
    item_ids: list[int]


class ProspectiveScoreOut(BaseModel):
    n_checks: int
    recall_rate: Optional[float] = None
    recall_rate_ci_low: Optional[float] = None
    recall_rate_ci_high: Optional[float] = None
    change_pct: Optional[float] = None
    change_ci_low_pct: Optional[float] = None
    change_ci_high_pct: Optional[float] = None
    trend_available: bool = False
    trend_note: Optional[str] = None
    memory_aid_disclaimer: str
