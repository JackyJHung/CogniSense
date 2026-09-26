"""
Basic smoke tests. Run:
    cd backend
    pip install -r requirements.txt -r requirements-dev.txt
    pytest tests/

ISOLATION NOTE
--------------
These tests used to run `TestClient(app)` directly against the real SQLite
database at backend/db/cognisense.db, signing up two hardcoded usernames
(`test_user_1`, `flow_user`). That made the suite single-use: the first run
passed and wrote those users into the dev database, and every run after it
failed on `assert r.status_code == 201` because the username was taken. It also
meant running the tests quietly polluted real data, and
`test_full_daily_flow`'s `len(series) == 1` assertion only held on a virgin
database.

Each test now gets a fresh in-memory database via `dependency_overrides`, so the
suite is repeatable and touches nothing on disk.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # one shared in-memory DB across connections
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Import every model so create_all sees the full metadata.
    from app.models import checkin, image_association, reminder, user  # noqa: F401
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "CogniSense API"
    assert "disclaimer" in body
    assert "NOT a medical diagnostic device" in body["disclaimer"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_signup_and_login(client):
    # Signup
    payload = {
        "username": "test_user_1",
        "password": "securepass",
        "age": 70,
        "gender": "female",
        "race": "black",
        "wake_time": "07:00:00",
        "sleep_time": "22:30:00",
    }
    r = client.post("/users/signup", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    # Signup now issues a session alongside the profile.
    assert body["user"]["username"] == "test_user_1"
    assert body["user"]["age"] == 70
    assert body["token"] and body["token_type"] == "bearer"

    # Duplicate signup fails
    r2 = client.post("/users/signup", json=payload)
    assert r2.status_code == 400

    # Login
    r3 = client.post("/users/login", json={"username": "test_user_1", "password": "securepass"})
    assert r3.status_code == 200
    assert r3.json()["token"] != body["token"], "each login issues a fresh session"

    # Wrong password
    r4 = client.post("/users/login", json={"username": "test_user_1", "password": "wrong"})
    assert r4.status_code == 401


def test_full_daily_flow(client):
    # Signup
    payload = {
        "username": "flow_user",
        # 8 characters minimum since the password-change and recovery flows
        # landed; "abcdef" no longer passes validation.
        "password": "abcdefgh",
        "age": 72,
        "gender": "male",
        "race": "hispanic",
        "wake_time": "06:30:00",
        "sleep_time": "22:00:00",
    }
    r = client.post("/users/signup", json=payload)
    assert r.status_code == 201, r.text
    auth = r.json()
    user_id = auth["user"]["id"]
    # Everything past signup requires the bearer token.
    client.headers["Authorization"] = f"Bearer {auth['token']}"

    # Morning
    r = client.post("/checkins/morning", json={
        "user_id": user_id,
        "planned_activities": "walk the dog, buy groceries, call sister, read book",
    })
    assert r.status_code == 201, r.text
    morning = r.json()
    assert len(morning["presented_associations"]) == 5
    assert "disclaimer" in morning

    # Midday
    r = client.post("/checkins/midday", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "what_user_has_done": "walked dog bought groceries",
        "planned_remainder": "call sister read book",
        "response_latency_ms": 1400,
    })
    assert r.status_code == 201

    # Evening — answer most correctly
    responses = []
    for i, assoc in enumerate(morning["presented_associations"]):
        answer = assoc["object_name"] if i < 4 else "wrong"
        responses.append({
            "association_id": assoc["id"],
            "user_answer": answer,
            "response_latency_ms": 1200 + i * 100,
        })

    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": "walked dog grocery store called sister read book",
        "association_responses": responses,
    })
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["association_accuracy"] == 0.8   # 4 out of 5
    assert ev["daily_cognitive_score"] is not None
    assert 0 <= ev["daily_cognitive_score"] <= 1
    assert "disclaimer" in ev

    # Risk comparison
    r = client.get(f"/reports/risk-comparison/{user_id}")
    assert r.status_code == 200
    rc = r.json()
    assert "peer_expected_prevalence_pct" in rc
    assert rc["peer_expected_prevalence_pct"] > 0
    assert len(rc["suggestions"]) >= 3
    assert len(rc["citations"]) > 0

    # Daily suggestions
    r = client.get(f"/reports/daily-suggestions/{user_id}")
    assert r.status_code == 200
    ds = r.json()
    assert len(ds["suggestions"]) == 3
    assert "Lancet" in ds["lancet_risk_factor_source"]

    # Trend
    r = client.get(f"/reports/trend/{user_id}")
    assert r.status_code == 200
    assert len(r.json()["series"]) == 1


def test_no_recording_means_no_speech_score(client):
    """Without audio there is no speech measurement, and none may be reported.

    The daily composite still uses a neutral stand-in for the speech slot, but
    the evening result used to store and show that stand-in, 0.75, as if it
    were the user's measured speech biomarker.
    """
    r = client.post("/users/signup", json={
        "username": "quiet_user", "password": "abcdefgh", "age": 68, "gender": "female",
        "race": "white", "wake_time": "07:00:00", "sleep_time": "22:00:00",
    })
    auth = r.json()
    client.headers["Authorization"] = f"Bearer {auth['token']}"
    uid = auth["user"]["id"]

    morning = client.post("/checkins/morning", json={
        "user_id": uid, "planned_activities": "garden, post office",
    }).json()
    evening = client.post("/checkins/evening", json={
        "user_id": uid,
        "morning_checkin_id": morning["id"],
        "recalled_activities": "garden",
        "association_responses": [
            {"association_id": a["id"], "user_answer": a["object_name"], "response_latency_ms": 1500}
            for a in morning["presented_associations"]
        ],
    })
    assert evening.status_code == 201, evening.text
    body = evening.json()
    assert body["speech_biomarker_score"] is None
    assert body["daily_cognitive_score"] is not None


def test_evening_test_is_taken_once(client):
    """A second evening test for the same morning is refused with the first result.

    A retake has already seen the answers, so it measures nothing new. It used to
    be scored anyway: stored beside the first attempt, added to the check-in
    count that feeds every later score, and shown as the day's result -- while
    the reports count only the first attempt.
    """
    r = client.post("/users/signup", json={
        "username": "retake_user", "password": "abcdefgh", "age": 66, "gender": "male",
        "race": "aapi", "wake_time": "07:00:00", "sleep_time": "22:00:00",
    })
    auth = r.json()
    client.headers["Authorization"] = f"Bearer {auth['token']}"
    uid = auth["user"]["id"]

    morning = client.post("/checkins/morning", json={
        "user_id": uid, "planned_activities": "library, pharmacy",
    }).json()
    cues = morning["presented_associations"]

    def evening(answer):
        return client.post("/checkins/evening", json={
            "user_id": uid,
            "morning_checkin_id": morning["id"],
            "recalled_activities": "library",
            "association_responses": [
                {"association_id": a["id"], "user_answer": answer(a), "response_latency_ms": 1500}
                for a in cues
            ],
        })

    first = evening(lambda a: "no idea")
    assert first.status_code == 201, first.text
    assert first.json()["association_accuracy"] == 0.0

    # Now with every answer right -- which is exactly why it must not count.
    retake = evening(lambda a: a["object_name"])
    assert retake.status_code == 409, retake.text
    detail = retake.json()["detail"]
    assert detail["code"] == "evening_already_submitted"
    assert detail["existing"]["id"] == first.json()["id"]
    assert detail["existing"]["association_accuracy"] == 0.0
    assert "disclaimer" in detail["existing"]

    # Nothing was stored for the retake.
    days = [p for p in client.get(f"/reports/trend/{uid}").json()["points"] if p["attempts"]]
    assert len(days) == 1 and days[0]["attempts"] == 1
