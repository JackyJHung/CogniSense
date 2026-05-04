"""
Basic smoke tests. Run:
    cd backend
    pip install pytest httpx
    pytest tests/
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "CogniSense API"
    assert "disclaimer" in body
    assert "NOT a medical diagnostic device" in body["disclaimer"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_signup_and_login():
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
    user = r.json()
    assert user["username"] == "test_user_1"
    assert user["age"] == 70

    # Duplicate signup fails
    r2 = client.post("/users/signup", json=payload)
    assert r2.status_code == 400

    # Login
    r3 = client.post("/users/login", json={"username": "test_user_1", "password": "securepass"})
    assert r3.status_code == 200

    # Wrong password
    r4 = client.post("/users/login", json={"username": "test_user_1", "password": "wrong"})
    assert r4.status_code == 401


def test_full_daily_flow():
    # Signup
    payload = {
        "username": "flow_user",
        "password": "abcdef",
        "age": 72,
        "gender": "male",
        "race": "hispanic",
        "wake_time": "06:30:00",
        "sleep_time": "22:00:00",
    }
    r = client.post("/users/signup", json=payload)
    user_id = r.json()["id"]

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
