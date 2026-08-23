"""Shared pytest fixtures.

Every test gets a fresh in-memory SQLite database wired into the FastAPI app
through a `get_db` dependency override, so tests never touch `backend/db/`.

Run:
    cd backend
    pip install -r requirements.txt pytest pytest-cov httpx
    pytest tests/
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.checkin import EveningCheckin
from app.models.user import User


@pytest.fixture
def session_factory():
    """Fresh in-memory DB per test, shared across connections via StaticPool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def _isolated_db(session_factory):
    """Autouse so the module-level TestClient in test_backend.py is isolated too."""
    return session_factory


@pytest.fixture
def db(session_factory):
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


def _signup_payload(**overrides):
    payload = {
        "username": "fixture_user",
        "password": "securepass",
        "age": 70,
        "gender": "female",
        "race": "black",
        "wake_time": "07:00:00",
        "sleep_time": "22:30:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def signup_payload():
    """Factory for a valid /users/signup body."""
    return _signup_payload


@pytest.fixture
def user_id(client):
    r = client.post("/users/signup", json=_signup_payload())
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def make_history(db):
    """Insert synthetic evening check-ins for a user at given day offsets."""

    def _make(user_id: int, scores_by_days_ago: dict[int, float]):
        for days_ago, score in scores_by_days_ago.items():
            db.add(
                EveningCheckin(
                    user_id=user_id,
                    morning_checkin_id=1,
                    timestamp=datetime.utcnow() - timedelta(days=days_ago),
                    recalled_activities="walked the dog",
                    activity_recall_accuracy=score,
                    association_responses=[],
                    association_accuracy=score,
                    avg_response_latency_ms=1500,
                    daily_cognitive_score=score,
                )
            )
        user = db.query(User).filter(User.id == user_id).one()
        user.cumulative_checkin_count = len(scores_by_days_ago)
        user.cumulative_recall_score = sum(scores_by_days_ago.values()) / len(scores_by_days_ago)
        db.commit()

    return _make
