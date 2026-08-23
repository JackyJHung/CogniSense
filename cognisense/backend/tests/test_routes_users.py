"""Unit tests for app/routes/users.py."""

import pytest

from app.models.user import User
from app.routes.users import pwd_context


def test_signup_persists_a_hashed_password(client, db, signup_payload):
    r = client.post("/users/signup", json=signup_payload(username="alice", password="hunter22"))
    assert r.status_code == 201, r.text

    body = r.json()
    assert body["username"] == "alice"
    assert "password" not in body and "hashed_password" not in body

    stored = db.query(User).filter(User.username == "alice").one()
    assert stored.hashed_password != "hunter22"
    assert pwd_context.verify("hunter22", stored.hashed_password)
    assert stored.cumulative_checkin_count == 0


def test_signup_rejects_duplicate_usernames(client, signup_payload):
    client.post("/users/signup", json=signup_payload(username="bob"))
    r = client.post("/users/signup", json=signup_payload(username="bob"))
    assert r.status_code == 400
    assert r.json()["detail"] == "Username already taken"


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": "ab"},                 # min_length 3
        {"username": "x" * 33},             # max_length 32
        {"password": "short"},              # min_length 6
        {"age": 17},                        # ge 18
        {"age": 121},                       # le 120
        {"gender": "unspecified"},          # not in Literal
        {"race": "martian"},                # not in Literal
        {"wake_time": "not-a-time"},
    ],
)
def test_signup_validation_rejects_bad_input(client, signup_payload, overrides):
    r = client.post("/users/signup", json=signup_payload(**overrides))
    assert r.status_code == 422


def test_signup_requires_all_fields(client):
    r = client.post("/users/signup", json={"username": "carol", "password": "secret1"})
    assert r.status_code == 422


def test_login_succeeds_with_correct_credentials(client, signup_payload):
    created = client.post("/users/signup", json=signup_payload(username="dave")).json()
    r = client.post("/users/login", json={"username": "dave", "password": "securepass"})
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_login_rejects_wrong_password(client, signup_payload):
    client.post("/users/signup", json=signup_payload(username="erin"))
    r = client.post("/users/login", json={"username": "erin", "password": "nope123"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"


def test_login_rejects_unknown_username(client):
    r = client.post("/users/login", json={"username": "ghost", "password": "whatever"})
    assert r.status_code == 401


def test_get_user_returns_profile_without_secrets(client, user_id):
    r = client.get(f"/users/{user_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == user_id
    assert body["age"] == 70
    assert body["wake_time"] == "07:00:00"
    assert "hashed_password" not in body


def test_get_user_404_for_unknown_id(client):
    r = client.get("/users/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"
