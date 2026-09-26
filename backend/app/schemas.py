"""Pydantic schemas for API request/response bodies."""

from datetime import datetime, time
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app import timezones


Gender = Literal["female", "male", "nonbinary", "other", "prefer_not"]
Race = Literal["white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not"]


# ---------- User ----------

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    # Raised from 6 to 8 alongside the password-change and recovery flows, so a
    # single floor applies wherever a password is set. Existing accounts are
    # unaffected -- their stored hashes are never re-validated.
    password: str = Field(..., min_length=8, max_length=200)
    age: int = Field(..., ge=18, le=120)
    gender: Gender
    race: Race
    wake_time: time
    sleep_time: time
    # IANA name from the client, e.g. the browser's
    # Intl.DateTimeFormat().resolvedOptions().timeZone. Optional: a client that
    # cannot tell leaves the account's zone unknown, counted as UTC.
    timezone: Optional[str] = Field(None, max_length=timezones.MAX_NAME_LENGTH)

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else timezones.validate(v)


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
    email: Optional[str] = None
    email_verified_at: Optional[datetime] = None
    # None until a client has reported it; days are then counted in UTC.
    timezone: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str
    # The device's zone, adopted only by an account that has none yet.
    # Deliberately NOT validated here: a browser reporting something odd must
    # never stop a person logging in. The route checks it and ignores a bad one.
    timezone: Optional[str] = None


class TimezoneUpdate(BaseModel):
    """An explicit choice from the settings page, so an unknown name is a 422."""
    timezone: str = Field(..., max_length=timezones.MAX_NAME_LENGTH)

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, v: str) -> str:
        return timezones.validate(v)


class AuthOut(BaseModel):
    """Returned by signup and login. `token` is shown exactly once."""
    user: UserOut
    token: str
    token_type: str = "bearer"
    expires_at: datetime


class LogoutRequest(BaseModel):
    # Log out on every device rather than just this one.
    all_devices: bool = False


# Minimum for any NEWLY set password. Applies to signup, password change and
# recovery alike, so there is one rule rather than three.
MIN_PASSWORD_LENGTH = 8


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)

    @model_validator(mode="after")
    def must_actually_change(self):
        if self.current_password == self.new_password:
            raise ValueError("the new password must be different from the current one")
        return self


class RecoveryCodesOut(BaseModel):
    """Returned exactly once, at generation. The codes are not stored in clear."""
    codes: list[str]
    generated: int
    warning: str


class RecoverRequest(BaseModel):
    username: str
    code: str = Field(..., max_length=100)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)


class RecoveryStatusOut(BaseModel):
    codes_remaining: int
    codes_used: int
    has_codes: bool
    email: Optional[str] = None
    email_verified: bool = False
    email_delivery_enabled: bool = False


class SetEmailRequest(BaseModel):
    # Changing the recovery address is a credential operation, so it needs the
    # password: otherwise a borrowed session could redirect recovery to an
    # attacker's inbox and take the account permanently.
    current_password: str
    email: EmailStr


class EmailTokenRequest(BaseModel):
    token: str = Field(..., max_length=200)


class ForgotPasswordRequest(BaseModel):
    # Username or email; one field so the form does not force a choice.
    identifier: str = Field(..., max_length=320)


class ResetWithTokenRequest(BaseModel):
    token: str = Field(..., max_length=200)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)


class GenericMessageOut(BaseModel):
    """Deliberately says the same thing whether or not the account exists."""
    ok: bool = True
    message: str


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


# ---------- Web Push ----------

class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """Mirrors the browser's PushSubscription.toJSON() shape."""
    endpoint: str = Field(..., max_length=2000)
    keys: PushKeys


class PushSubscribeRequest(BaseModel):
    user_id: int
    subscription: PushSubscriptionIn
    # The device's IANA zone. Quiet hours are computed from the user's stored
    # zone; this only fills it in for an account that has none, on the same
    # terms as login. It replaced utc_offset_minutes, which an older client may
    # still send -- extra fields are ignored, so that does no harm.
    timezone: Optional[str] = None
    user_agent: Optional[str] = Field(None, max_length=400)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., max_length=2000)


class PushStatusOut(BaseModel):
    enabled: bool
    devices: int
    last_push_at: Optional[datetime] = None
    cooldown_hours: int
    quiet_hours: str
    currently_awake: bool
    scheduler_running: bool


class PushSendResultOut(BaseModel):
    sent: int
    failed: int
    removed: int
    devices: int
    detail: Optional[str] = None


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
