"""Authentication and authorisation: proof the IDOR is actually closed.

Before this, every endpoint took `user_id` from the path or body and trusted it.
`GET /reminders/4` handed back user 4's reminders to anybody who asked. These
tests exist so that regressing it fails loudly rather than silently.

The important ones are in the "cross-account" section: they run as a REAL,
fully-authenticated user (Mallory) and try to reach a second real user's data.
Authentication alone does not stop that -- Mallory's token is perfectly valid --
so those tests are what prove the authorisation layer, not just the login.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import create_session, hash_token  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.push import PushSubscription  # noqa: E402
from app.models.reminder import STATUS_PENDING, ReminderCheck, ReminderItem  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes.users import pwd_context  # noqa: E402


@pytest.fixture()
def env():
    """Two real accounts: `victim` with data, `mallory` with a valid token."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import (  # noqa: F401
        checkin, image_association, push, reminder, session as _s, user,
    )
    Base.metadata.create_all(bind=engine)

    db = TestingSession()

    def mk(uid, name):
        # A REAL bcrypt hash, not a placeholder: passlib refuses to verify
        # against anything it cannot identify, so a fake one would make the
        # login tests exercise the error path instead of the success path.
        u = User(id=uid, username=name,
                 hashed_password=pwd_context.hash(f"{name}-password"),
                 age=70, gender="female", race="white",
                 wake_time=dtime(7), sleep_time=dtime(22))
        db.add(u)
        return u

    victim = mk(1, "victim")
    mallory = mk(2, "mallory")
    db.commit()

    # The victim's private data.
    item = ReminderItem(id=100, user_id=victim.id, description="collect my prescription",
                        status=STATUS_PENDING)
    check = ReminderCheck(id=200, user_id=victim.id, active_item_ids=[100], n_items_active=1)
    sub = PushSubscription(id=300, user_id=victim.id,
                           endpoint="https://push.example/victim", p256dh="k", auth="a")
    db.add_all([item, check, sub])
    db.commit()

    tokens = {
        "victim": create_session(db, victim),
        "mallory": create_session(db, mallory),
    }

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        yield client, db, tokens
    fastapi_app.dependency_overrides.clear()
    db.close()


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Unauthenticated
# --------------------------------------------------------------------------

PROTECTED = [
    ("GET", "/users/1"),
    ("GET", "/users/me"),
    ("GET", "/reminders/1"),
    ("GET", "/reminders/1/due"),
    ("POST", "/reminders/1/check"),
    ("GET", "/reminders/1/prospective-score"),
    ("GET", "/reports/risk-comparison/1"),
    ("GET", "/reports/daily-suggestions/1"),
    ("GET", "/reports/trend/1"),
    ("GET", "/checkins/morning/today/1"),
    ("GET", "/push/status/1"),
    ("POST", "/push/test/1"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_no_token_is_rejected(env, method, path):
    client, _, _ = env
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} answered without a token"
    assert r.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.parametrize("header", [
    {"Authorization": "Bearer not-a-real-token"},
    {"Authorization": "Bearer "},
    {"Authorization": "Basic abc123"},
    {"Authorization": "totally-malformed"},
])
def test_bad_tokens_are_rejected(env, header):
    client, _, _ = env
    assert client.get("/reminders/1", headers=header).status_code == 401


def test_expired_token_is_rejected_and_deleted(env):
    client, db, _ = env
    user = db.query(User).get(1)
    raw = create_session(db, user)

    session_row = db.query(UserSession).filter(
        UserSession.token_hash == hash_token(raw)
    ).first()
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert client.get("/reminders/1", headers=hdr(raw)).status_code == 401
    db.expire_all()
    assert db.query(UserSession).filter(
        UserSession.token_hash == hash_token(raw)
    ).first() is None, "an expired session should be cleaned up, not just refused"


# --------------------------------------------------------------------------
# Cross-account: the IDOR itself
# --------------------------------------------------------------------------

def test_mallory_cannot_read_the_victims_reminders(env):
    """The original bug, in one test.

    Mallory is fully logged in. Her token is valid. She simply asks for user 1's
    reminders instead of her own.
    """
    client, _, tokens = env
    r = client.get("/reminders/1", headers=hdr(tokens["mallory"]))
    assert r.status_code == 403
    assert "prescription" not in r.text


@pytest.mark.parametrize("path", [
    "/users/1",
    "/reminders/1",
    "/reminders/1/due",
    "/reminders/1/prospective-score",
    "/reports/risk-comparison/1",
    "/reports/daily-suggestions/1",
    "/reports/trend/1",
    "/checkins/morning/today/1",
    "/push/status/1",
])
def test_every_user_scoped_get_refuses_another_account(env, path):
    client, _, tokens = env
    r = client.get(path, headers=hdr(tokens["mallory"]))
    assert r.status_code == 403, f"{path} served another user's data"


@pytest.mark.parametrize("path", [
    "/reminders/1/check",
    "/push/test/1",
])
def test_every_user_scoped_post_refuses_another_account(env, path):
    client, _, tokens = env
    assert client.post(path, headers=hdr(tokens["mallory"])).status_code == 403


def test_body_user_id_cannot_be_spoofed(env):
    """user_id in the BODY is checked too -- require_self only covers paths."""
    client, _, tokens = env
    r = client.post("/reminders", headers=hdr(tokens["mallory"]),
                    json={"user_id": 1, "description": "planted by mallory"})
    assert r.status_code == 403


def test_mallory_cannot_answer_the_victims_check(env):
    """Resource-keyed route. The response would contain the victim's whole list.

    404 rather than 403, so the reply does not confirm that check 200 exists.
    """
    client, _, tokens = env
    r = client.post("/reminders/check/200/recall", headers=hdr(tokens["mallory"]),
                    json={"recall_text": "guessing"})
    assert r.status_code == 404
    assert "prescription" not in r.text


def test_mallory_cannot_attach_a_photo_to_the_victims_reminder(env):
    client, _, tokens = env
    r = client.post(
        "/reminders/100/image", headers=hdr(tokens["mallory"]),
        files={"image": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert r.status_code == 404


def test_mallory_cannot_unsubscribe_the_victims_device(env):
    """Silently disabling someone's reminders is the quietest possible attack."""
    client, db, tokens = env
    r = client.post("/push/unsubscribe", headers=hdr(tokens["mallory"]),
                    json={"endpoint": "https://push.example/victim"})
    assert r.status_code == 200
    assert r.json()["removed"] == 0
    db.expire_all()
    assert db.query(PushSubscription).filter(PushSubscription.id == 300).first() is not None


def test_the_victim_can_still_reach_their_own_data(env):
    """The checks must not have locked out the legitimate owner."""
    client, _, tokens = env
    r = client.get("/reminders/1", headers=hdr(tokens["victim"]))
    assert r.status_code == 200
    assert any("prescription" in (i["description"] or "") for i in r.json())


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------

def test_logout_really_ends_the_session(env):
    """Logout used to be client-side only; the credential stayed valid forever."""
    client, _, tokens = env
    token = tokens["victim"]

    assert client.get("/users/me", headers=hdr(token)).status_code == 200
    assert client.post("/users/logout", headers=hdr(token)).status_code == 200
    assert client.get("/users/me", headers=hdr(token)).status_code == 401


def test_logout_all_devices_revokes_every_session(env):
    client, db, _ = env
    user = db.query(User).get(1)
    a, b = create_session(db, user), create_session(db, user)

    r = client.post("/users/logout", headers=hdr(a), json={"all_devices": True})
    assert r.status_code == 200
    assert r.json()["scope"] == "all"

    assert client.get("/users/me", headers=hdr(a)).status_code == 401
    assert client.get("/users/me", headers=hdr(b)).status_code == 401


def test_logging_out_one_device_leaves_the_others_alone(env):
    client, db, _ = env
    user = db.query(User).get(1)
    phone, laptop = create_session(db, user), create_session(db, user)

    client.post("/users/logout", headers=hdr(phone))

    assert client.get("/users/me", headers=hdr(phone)).status_code == 401
    assert client.get("/users/me", headers=hdr(laptop)).status_code == 200


def test_raw_tokens_are_never_stored(env):
    """A leaked database must not yield usable credentials."""
    client, db, tokens = env
    raw = tokens["victim"]

    stored = {row.token_hash for row in db.query(UserSession).all()}
    assert raw not in stored
    assert hash_token(raw) in stored
    assert all(len(h) == 64 for h in stored), "expected SHA-256 hex"


def test_login_does_not_reveal_whether_a_username_exists(env):
    client, _, _ = env
    missing = client.post("/users/login",
                          json={"username": "no-such-person", "password": "x"})
    wrong = client.post("/users/login", json={"username": "victim", "password": "x"})

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


def test_login_works_with_the_right_password(env):
    """Guards the timing-equaliser change: it must not break real logins."""
    client, _, _ = env
    r = client.post("/users/login",
                    json={"username": "victim", "password": "victim-password"})
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "victim"
    assert r.json()["token"]


def test_a_corrupt_stored_hash_is_a_401_not_a_500(env):
    """A malformed password hash must refuse the login, not crash the request.

    passlib raises UnknownHashError on a digest it cannot parse. Unhandled, that
    became a 500 -- which both broke the endpoint and distinguished "this
    account exists but its hash is broken" from an ordinary wrong password.
    """
    client, db, _ = env
    user = db.query(User).get(2)
    user.hashed_password = "not-a-bcrypt-hash"
    db.commit()

    r = client.post("/users/login",
                    json={"username": "mallory", "password": "anything"})
    assert r.status_code == 401, "a corrupt hash should refuse cleanly"
    assert r.json()["detail"] == "Invalid credentials"


def test_me_identifies_the_token_holder(env):
    client, _, tokens = env
    assert client.get("/users/me", headers=hdr(tokens["victim"])).json()["username"] == "victim"
    assert client.get("/users/me", headers=hdr(tokens["mallory"])).json()["username"] == "mallory"


def test_tokens_are_unguessable(env):
    """secrets.token_urlsafe(32) -> 256 bits of entropy, 43 characters."""
    client, db, _ = env
    user = db.query(User).get(1)
    issued = {create_session(db, user) for _ in range(20)}
    assert len(issued) == 20, "tokens must not repeat"
    assert all(len(t) >= 40 for t in issued)
