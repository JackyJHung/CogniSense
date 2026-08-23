"""
Basic smoke tests. Run:
    cd backend
    pip install pytest httpx
    pytest tests/
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Isolated throwaway database so runs do not accumulate state.
os.environ["COGNISENSE_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")

from fastapi.testclient import TestClient
from app.database import init_db
from app.main import app

init_db()
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


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    user = body["user"]
    assert user["username"] == "test_user_1"
    assert user["age"] == 70

    # Duplicate signup fails
    r2 = client.post("/users/signup", json=payload)
    assert r2.status_code == 400

    # Login
    r3 = client.post("/users/login", json={"username": "test_user_1", "password": "securepass"})
    assert r3.status_code == 200
    token = r3.json()["access_token"]

    # Wrong password
    r4 = client.post("/users/login", json={"username": "test_user_1", "password": "wrong"})
    assert r4.status_code == 401

    # Token grants access to own profile
    r5 = client.get("/users/me", headers=auth_header(token))
    assert r5.status_code == 200
    assert r5.json()["username"] == "test_user_1"


def test_endpoints_require_authentication():
    for method, path in [
        ("post", "/checkins/morning"),
        ("post", "/checkins/midday"),
        ("post", "/checkins/evening"),
    ]:
        assert getattr(client, method)(path, json={}).status_code == 401
    for path in ["/users/1", "/reports/risk-comparison/1", "/reports/trend/1",
                 "/reports/daily-suggestions/1"]:
        assert client.get(path).status_code == 401

    assert client.get("/users/1", headers=auth_header("not-a-jwt")).status_code == 401


def test_cannot_read_another_users_data():
    def make(username):
        r = client.post("/users/signup", json={
            "username": username,
            "password": "securepass",
            "age": 68,
            "gender": "female",
            "race": "white",
            "wake_time": "07:00:00",
            "sleep_time": "22:00:00",
        })
        assert r.status_code == 201, r.text
        return r.json()

    victim = make("victim_user")
    attacker = make("attacker_user")
    headers = auth_header(attacker["access_token"])
    victim_id = victim["user"]["id"]

    assert client.get(f"/users/{victim_id}", headers=headers).status_code == 403
    assert client.get(f"/reports/trend/{victim_id}", headers=headers).status_code == 403
    assert client.get(
        f"/reports/risk-comparison/{victim_id}", headers=headers
    ).status_code == 403


def test_cannot_grade_another_users_morning_checkin():
    def signup(username):
        r = client.post("/users/signup", json={
            "username": username,
            "password": "securepass",
            "age": 70,
            "gender": "male",
            "race": "black",
            "wake_time": "07:00:00",
            "sleep_time": "22:00:00",
        })
        return r.json()["access_token"]

    owner = auth_header(signup("morning_owner"))
    other = auth_header(signup("morning_other"))

    r = client.post(
        "/checkins/morning",
        json={"planned_activities": "walk the dog"},
        headers=owner,
    )
    morning_id = r.json()["id"]

    r = client.post(
        "/checkins/evening",
        json={
            "morning_checkin_id": morning_id,
            "recalled_activities": "walked the dog",
            "association_responses": [],
        },
        headers=other,
    )
    assert r.status_code == 404


def test_audio_upload_rejects_traversal_filename():
    r = client.post("/users/signup", json={
        "username": "audio_user",
        "password": "securepass",
        "age": 70,
        "gender": "male",
        "race": "white",
        "wake_time": "07:00:00",
        "sleep_time": "22:00:00",
    })
    headers = auth_header(r.json()["access_token"])
    morning_id = client.post(
        "/checkins/morning",
        json={"planned_activities": "read a book"},
        headers=headers,
    ).json()["id"]

    r = client.post(
        f"/checkins/morning/{morning_id}/audio",
        files={"audio": ("../../../../tmp/pwned.py", b"not audio", "audio/wav")},
        headers=headers,
    )
    assert r.status_code == 415
    assert not Path("/tmp/pwned.py").exists()


def test_full_daily_flow():
    # Signup
    payload = {
        "username": "flow_user",
        "password": "abcdefgh",
        "age": 72,
        "gender": "male",
        "race": "hispanic",
        "wake_time": "06:30:00",
        "sleep_time": "22:00:00",
    }
    r = client.post("/users/signup", json=payload)
    body = r.json()
    user_id = body["user"]["id"]
    headers = auth_header(body["access_token"])

    # Morning
    r = client.post("/checkins/morning", json={
        "planned_activities": "walk the dog, buy groceries, call sister, read book",
    }, headers=headers)
    assert r.status_code == 201, r.text
    morning = r.json()
    assert len(morning["presented_associations"]) == 5
    assert "disclaimer" in morning

    # Midday
    r = client.post("/checkins/midday", json={
        "morning_checkin_id": morning["id"],
        "what_user_has_done": "walked dog bought groceries",
        "planned_remainder": "call sister read book",
        "response_latency_ms": 1400,
    }, headers=headers)
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
        "morning_checkin_id": morning["id"],
        "recalled_activities": "walked dog grocery store called sister read book",
        "association_responses": responses,
    }, headers=headers)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["association_accuracy"] == 0.8   # 4 out of 5
    assert ev["daily_cognitive_score"] is not None
    assert 0 <= ev["daily_cognitive_score"] <= 1
    assert "disclaimer" in ev

    # Risk comparison
    r = client.get(f"/reports/risk-comparison/{user_id}", headers=headers)
    assert r.status_code == 200
    rc = r.json()
    assert "peer_expected_prevalence_pct" in rc
    assert rc["peer_expected_prevalence_pct"] > 0
    assert len(rc["suggestions"]) >= 3
    assert len(rc["citations"]) > 0

    # Daily suggestions
    r = client.get(f"/reports/daily-suggestions/{user_id}", headers=headers)
    assert r.status_code == 200
    ds = r.json()
    assert len(ds["suggestions"]) == 3
    assert "Lancet" in ds["lancet_risk_factor_source"]

    # Trend
    r = client.get(f"/reports/trend/{user_id}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["series"]) == 1
