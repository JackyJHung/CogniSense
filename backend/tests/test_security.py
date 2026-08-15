"""Brute-force throttling, password change, recovery codes, and CSRF.

The load-bearing tests here are:

  test_throttle_refuses_before_any_password_hashing
      The throttle exists as much to stop a DoS as a guessing attack. bcrypt
      burns ~250ms of CPU per call, so a limit that checks AFTER hashing does
      not protect the server at all. This asserts the ordering directly.

  test_cookie_session_without_csrf_header_is_refused
      Moving the session into an HttpOnly cookie is only safe if CSRF is
      handled. This is the test that says so.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import ratelimit  # noqa: E402
from app.auth import create_session  # noqa: E402
from app.csrf import CSRF_COOKIE, SESSION_COOKIE  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.security import LoginAttempt, RecoveryCode  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes.users import pwd_context  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import (  # noqa: F401
        checkin, image_association, push, reminder, security, session as _s, user,
    )
    Base.metadata.create_all(bind=engine)

    db = TestingSession()
    db.add(User(id=1, username="alice", hashed_password=pwd_context.hash(PASSWORD),
                age=70, gender="female", race="white",
                wake_time=dtime(7), sleep_time=dtime(22)))
    db.commit()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        yield client, db
    fastapi_app.dependency_overrides.clear()
    db.close()


def login(client, password=PASSWORD, username="alice"):
    return client.post("/users/login", json={"username": username, "password": password})


def csrf_headers(client) -> dict:
    """The double-submit header, read from the readable cookie."""
    token = client.cookies.get(CSRF_COOKIE)
    return {"X-CSRF-Token": token} if token else {}


# ==========================================================================
# Brute-force throttling
# ==========================================================================

def test_repeated_failures_lock_the_account(env):
    client, db = env
    for _ in range(ratelimit.USER_MAX_FAILURES):
        assert login(client, "wrong").status_code == 401

    blocked = login(client, "wrong")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert "Too many failed attempts" in blocked.json()["detail"]


def test_lockout_blocks_even_the_correct_password(env):
    """Otherwise the limit is trivially bypassed by whoever finally guesses."""
    client, _ = env
    for _ in range(ratelimit.USER_MAX_FAILURES):
        login(client, "wrong")
    assert login(client, PASSWORD).status_code == 429


def test_throttle_refuses_before_any_password_hashing(env, monkeypatch):
    """The ordering that makes this a defence rather than an amplifier.

    bcrypt is ~250ms of CPU. If the limit were checked after verification, a
    locked-out attacker could still pin the processor with junk requests.
    """
    client, _ = env
    for _ in range(ratelimit.USER_MAX_FAILURES):
        login(client, "wrong")

    from app.routes import users as users_route

    def explode(*_a, **_kw):
        raise AssertionError("password verification ran on a locked-out request")

    monkeypatch.setattr(users_route, "_password_matches", explode)
    assert login(client, "wrong").status_code == 429


def test_a_successful_login_clears_the_user_counter(env):
    client, db = env
    for _ in range(ratelimit.USER_MAX_FAILURES - 1):
        login(client, "wrong")

    assert login(client, PASSWORD).status_code == 200

    db.expire_all()
    assert db.query(LoginAttempt).filter(
        LoginAttempt.key == "login:user:alice"
    ).first() is None


def test_the_ip_counter_survives_a_success(env, monkeypatch):
    """One success amid a flood is what credential stuffing looks like.

    Clearing the address counter on it would hand the attacker a free reset.
    """
    client, db = env
    ratelimit.register_failure(db, ["login:ip:testclient", "login:user:someone-else"])
    db.expire_all()
    before = db.query(LoginAttempt).filter(LoginAttempt.key == "login:ip:testclient").first()
    assert before.failures == 1

    assert login(client, PASSWORD).status_code == 200

    db.expire_all()
    after = db.query(LoginAttempt).filter(LoginAttempt.key == "login:ip:testclient").first()
    assert after is not None, "the IP counter must not be cleared by a success"


def test_lockouts_escalate(env):
    """A repeat offender waits longer each time, not the same 60s forever."""
    assert ratelimit._lockout_seconds(0) == ratelimit.BASE_LOCKOUT_SECONDS
    assert ratelimit._lockout_seconds(1) == ratelimit.BASE_LOCKOUT_SECONDS * 2
    assert ratelimit._lockout_seconds(2) == ratelimit.BASE_LOCKOUT_SECONDS * 4
    assert ratelimit._lockout_seconds(99) == ratelimit.MAX_LOCKOUT_SECONDS


def test_the_lock_expires(env):
    client, db = env
    for _ in range(ratelimit.USER_MAX_FAILURES):
        login(client, "wrong")
    assert login(client, PASSWORD).status_code == 429

    row = db.query(LoginAttempt).filter(
        LoginAttempt.key == "login:user:alice").first()
    row.locked_until = ratelimit._now() - timedelta(seconds=1)
    db.commit()

    assert login(client, PASSWORD).status_code == 200


def test_signup_is_throttled_too(env):
    """Signup runs bcrypt, so it is the same CPU-exhaustion surface as login."""
    client, db = env
    ratelimit.register_failure(db, ["login:ip:testclient"])
    row = db.query(LoginAttempt).filter(
        LoginAttempt.key == "login:ip:testclient").first()
    row.locked_until = ratelimit._now() + timedelta(minutes=5)
    db.commit()

    r = client.post("/users/signup", json={
        "username": "newcomer", "password": "a-long-enough-password", "age": 70,
        "gender": "female", "race": "white",
        "wake_time": "07:00:00", "sleep_time": "22:00:00",
    })
    assert r.status_code == 429


def test_a_login_lockout_does_not_bar_account_recovery(env):
    """The trap that scoped throttle keys exist to avoid.

    Somebody who has forgotten their password fails login several times and
    trips the lockout. Reaching for recovery is the correct next move -- and if
    login and recovery shared a throttle key, they would find it locked too.
    The only path back into the account would be barred at exactly the moment it
    was needed, by their own honest attempts.
    """
    client, _ = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    client.cookies.clear()

    for _ in range(ratelimit.USER_MAX_FAILURES + 1):
        login(client, "wrong")
    assert login(client, PASSWORD).status_code == 429, "login should now be locked"

    r = client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD,
    })
    assert r.status_code == 200, (
        "recovery must stay reachable while login is locked out"
    )


def test_recovery_and_login_throttles_are_independent(env):
    """The converse: exhausting recovery must not lock the password login."""
    client, _ = env
    for _ in range(ratelimit.USER_MAX_FAILURES + 1):
        client.post("/recovery/reset", json={
            "username": "alice", "code": "AAAAA-BBBBB-CCCCC-DDDDD",
            "new_password": NEW_PASSWORD})

    assert login(client, PASSWORD).status_code == 200


def test_stale_rows_are_pruned(env):
    client, db = env
    db.add(LoginAttempt(key="ip:ancient", failures=1,
                        window_started_at=ratelimit._now() - timedelta(days=3)))
    db.commit()
    assert ratelimit.prune(db) >= 1
    assert db.query(LoginAttempt).filter(LoginAttempt.key == "ip:ancient").first() is None


# ==========================================================================
# Cookies and CSRF
# ==========================================================================

def test_login_sets_an_httponly_session_cookie(env):
    client, _ = env
    r = login(client)
    assert r.status_code == 200

    raw = r.headers.get("set-cookie", "")
    assert SESSION_COOKIE in raw
    assert "httponly" in raw.lower(), "script must not be able to read the session"
    assert "samesite=strict" in raw.lower(), "the CSRF defence"
    assert client.cookies.get(CSRF_COOKIE), "the readable double-submit cookie"


def test_the_cookie_alone_authenticates(env):
    client, _ = env
    login(client)
    # No Authorization header anywhere; TestClient just replays the cookie.
    assert client.get("/users/me").json()["username"] == "alice"


def test_cookie_session_without_csrf_header_is_refused(env):
    """The whole justification for the double-submit token.

    A forged cross-site POST carries the cookie automatically but cannot read it
    to produce this header.
    """
    client, _ = env
    login(client)

    r = client.post("/reminders", json={"user_id": 1, "description": "forged"})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_cookie_session_with_csrf_header_is_accepted(env):
    client, _ = env
    login(client)
    r = client.post("/reminders", headers=csrf_headers(client),
                    json={"user_id": 1, "description": "legitimate"})
    assert r.status_code == 201


def test_a_wrong_csrf_token_is_refused(env):
    client, _ = env
    login(client)
    r = client.post("/reminders", headers={"X-CSRF-Token": "not-the-right-value"},
                    json={"user_id": 1, "description": "forged"})
    assert r.status_code == 403


def test_bearer_auth_needs_no_csrf_token(env):
    """Native clients send a header, which a browser never attaches for them.

    Header-authenticated requests are immune to CSRF by construction, so
    requiring a token would break the desktop and mobile apps for no gain.
    """
    client, db = env
    token = create_session(db, db.query(User).get(1))
    client.cookies.clear()

    r = client.post("/reminders", headers={"Authorization": f"Bearer {token}"},
                    json={"user_id": 1, "description": "from the desktop app"})
    assert r.status_code == 201


def test_safe_methods_need_no_csrf_token(env):
    client, _ = env
    login(client)
    assert client.get("/reminders/1").status_code == 200


def test_a_foreign_origin_is_refused(env):
    client, _ = env
    login(client)
    r = client.post(
        "/reminders",
        headers={**csrf_headers(client), "Origin": "https://evil.example"},
        json={"user_id": 1, "description": "forged"},
    )
    assert r.status_code == 403
    assert "origin" in r.json()["detail"].lower()


def test_logout_clears_the_cookies(env):
    client, _ = env
    login(client)
    r = client.post("/users/logout", headers=csrf_headers(client))
    assert r.status_code == 200
    assert not client.cookies.get(SESSION_COOKIE)
    assert client.get("/users/me").status_code == 401


# ==========================================================================
# Password change
# ==========================================================================

NEW_PASSWORD = "an-entirely-different-one"


def test_password_change_requires_the_current_password(env):
    client, _ = env
    login(client)
    r = client.post("/users/password", headers=csrf_headers(client),
                    json={"current_password": "wrong", "new_password": NEW_PASSWORD})
    assert r.status_code == 401


def test_password_change_works_and_the_new_password_logs_in(env):
    client, _ = env
    login(client)
    r = client.post("/users/password", headers=csrf_headers(client),
                    json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200

    client.cookies.clear()
    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_password_change_revokes_every_other_session(env):
    """The point of changing a password after a suspected compromise."""
    client, db = env
    stolen = create_session(db, db.query(User).get(1))
    login(client)

    client.post("/users/password", headers=csrf_headers(client),
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert client.get("/users/me",
                      headers={"Authorization": f"Bearer {stolen}"}).status_code == 401


def test_password_change_leaves_the_caller_logged_in(env):
    client, _ = env
    login(client)
    client.post("/users/password", headers=csrf_headers(client),
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert client.get("/users/me").status_code == 200


def test_the_new_password_must_differ_and_be_long_enough(env):
    client, _ = env
    login(client)
    same = client.post("/users/password", headers=csrf_headers(client),
                       json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 422

    short = client.post("/users/password", headers=csrf_headers(client),
                        json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422


# ==========================================================================
# Account recovery
# ==========================================================================

def test_codes_are_issued_once_and_stored_hashed(env):
    client, db = env
    login(client)
    r = client.post("/recovery/codes", headers=csrf_headers(client))
    assert r.status_code == 200

    body = r.json()
    codes = body["codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    assert "save these somewhere safe" in body["warning"].lower()

    stored = {row.code_hash for row in db.query(RecoveryCode).all()}
    for code in codes:
        assert code not in stored, "codes must never be stored in clear"


def test_a_code_resets_the_password(env):
    client, _ = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    client.cookies.clear()

    r = client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD,
    })
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "alice"

    client.cookies.clear()
    assert login(client, NEW_PASSWORD).status_code == 200


def test_a_code_works_only_once(env):
    client, _ = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    client.cookies.clear()

    first = client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD})
    assert first.status_code == 200

    client.cookies.clear()
    replay = client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": "yet-another-one"})
    assert replay.status_code == 401


def test_codes_are_accepted_regardless_of_case_and_dashes(env):
    """People retype these by hand, often anxious about their memory."""
    client, _ = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    client.cookies.clear()

    mangled = codes[0].lower().replace("-", " ")
    r = client.post("/recovery/reset", json={
        "username": "alice", "code": mangled, "new_password": NEW_PASSWORD})
    assert r.status_code == 200


def test_regenerating_invalidates_the_previous_unused_codes(env):
    client, _ = env
    login(client)
    old = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    client.post("/recovery/codes", headers=csrf_headers(client))
    client.cookies.clear()

    r = client.post("/recovery/reset", json={
        "username": "alice", "code": old[0], "new_password": NEW_PASSWORD})
    assert r.status_code == 401


def test_recovery_revokes_every_existing_session(env):
    """Recovering an account someone else has reached must evict them."""
    client, db = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    attacker = create_session(db, db.query(User).get(1))
    client.cookies.clear()

    client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD})

    assert client.get("/users/me",
                      headers={"Authorization": f"Bearer {attacker}"}).status_code == 401


def test_recovery_failures_are_indistinguishable(env):
    """No oracle for which usernames exist, or which codes are real."""
    client, _ = env
    unknown_user = client.post("/recovery/reset", json={
        "username": "nobody", "code": "AAAAA-BBBBB-CCCCC-DDDDD",
        "new_password": NEW_PASSWORD})
    bad_code = client.post("/recovery/reset", json={
        "username": "alice", "code": "AAAAA-BBBBB-CCCCC-DDDDD",
        "new_password": NEW_PASSWORD})

    assert unknown_user.status_code == bad_code.status_code == 401
    assert unknown_user.json() == bad_code.json()


def test_recovery_is_throttled(env):
    client, _ = env
    for _ in range(ratelimit.USER_MAX_FAILURES):
        client.post("/recovery/reset", json={
            "username": "alice", "code": "AAAAA-BBBBB-CCCCC-DDDDD",
            "new_password": NEW_PASSWORD})

    blocked = client.post("/recovery/reset", json={
        "username": "alice", "code": "AAAAA-BBBBB-CCCCC-DDDDD",
        "new_password": NEW_PASSWORD})
    assert blocked.status_code == 429


def test_recovery_status_counts_remaining_codes(env):
    client, _ = env
    login(client)
    before = client.get("/recovery/status").json()
    assert before["has_codes"] is False

    codes = client.post("/recovery/codes", headers=csrf_headers(client)).json()["codes"]
    after = client.get("/recovery/status").json()
    assert after["codes_remaining"] == 10 and after["codes_used"] == 0

    client.cookies.clear()
    client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD})
    login(client, NEW_PASSWORD)

    used = client.get("/recovery/status").json()
    assert used["codes_remaining"] == 9 and used["codes_used"] == 1


def test_generating_codes_requires_a_session(env):
    client, _ = env
    assert client.post("/recovery/codes").status_code == 401
