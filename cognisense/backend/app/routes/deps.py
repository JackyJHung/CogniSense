"""Shared route helpers for common DB lookups."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.checkin import MorningCheckin


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_morning_checkin_or_404(db: Session, morning_id: int) -> MorningCheckin:
    morning = db.query(MorningCheckin).filter(MorningCheckin.id == morning_id).first()
    if not morning:
        raise HTTPException(status_code=404, detail="Morning check-in not found")
    return morning
