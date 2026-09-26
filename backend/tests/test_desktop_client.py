"""The desktop client against the real API: the token, the 401, the response shape.

The desktop app broke silently when session auth landed. It kept the whole
login response as "the user" and never sent a credential, so every call after
login was a 401. These tests drive desktop_app/api_client.py through FastAPI's
TestClient -- the real routes, auth, validation and an in-memory database -- so
drift between what the desktop sends and what the API accepts fails here rather
than in front of a user.

THE COOKIE JAR IS SWITCHED OFF
Login also sets an HttpOnly session cookie for browsers, and TestClient would
store it and send it back. Every authenticated call would then pass whether or
not the client attached its token, and nothing here would prove the bearer
path. So the transport refuses cookies, exactly as the desktop app's own
session does, and the token is the only credential in play.
"""
from __future__ import annotations

import socket
import threading
import time
from http.cookiejar import DefaultCookiePolicy

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("requests")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from desktop_app.api_client import (  # noqa: E402
    AlreadySubmitted,
    ApiError,
    CogniSenseClient,
    ServerUnreachable,
    SessionExpired,
    describe,
)

PASSWORD = "correct-horse-battery"


class _Recorder:
    """The transport, plus a log of the headers on every outgoing request."""

    def __init__(self, inner):
        self.inner = inner
        self.sent: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.sent.append((method, url, dict(kwargs.get("headers") or {})))
        return self.inner.request(method, url, **kwargs)


@pytest.fixture()
def db_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import (  # noqa: F401
        checkin, image_association, push, reminder, security, session as _s, user,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def transport(db_factory):
    tc = TestClient(fastapi_app)
    tc.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))
    return _Recorder(tc)


@pytest.fixture()
def client(transport):
    return CogniSenseClient(base_url="http://testserver", session=transport)


def _signup(client, username="desk_user"):
    return client.signup(
        username=username, password=PASSWORD, age=70, gender="female",
        race="white", wake_time="07:00:00", sleep_time="22:30:00",
    )


# --------------------------------------------------------------------------
# Response unwrapping
# --------------------------------------------------------------------------

def test_signup_keeps_the_profile_not_the_envelope(client):
    user = _signup(client)

    assert user["username"] == "desk_user"
    assert "token" not in user and "user" not in user, (
        "the {user, token, ...} envelope was stored as the user"
    )
    assert client.user == user
    assert client.logged_in


def test_login_unwraps_the_user(client):
    _signup(client)
    client.forget()

    user = client.login("desk_user", PASSWORD)
    assert user["username"] == "desk_user"
    assert isinstance(user["id"], int)


# --------------------------------------------------------------------------
# The token
# --------------------------------------------------------------------------

def test_every_call_after_login_carries_the_bearer_token(client, transport):
    _signup(client)
    token = client._token
    sent_before = len(transport.sent)

    client.me()
    client.morning_today()
    client.risk_report()
    client.daily_suggestions()

    after_login = transport.sent[sent_before:]
    assert len(after_login) == 4
    for method, url, headers in after_login:
        assert headers.get("Authorization") == f"Bearer {token}", f"{method} {url} went without it"

    # And nothing else could have authenticated those calls.
    assert len(transport.inner.cookies) == 0


def test_a_call_before_login_goes_to_the_login_screen(client):
    with pytest.raises(SessionExpired):
        client.risk_report()


# --------------------------------------------------------------------------
# 401 handling
# --------------------------------------------------------------------------

def test_a_session_revoked_elsewhere_raises_session_expired(client, transport):
    """'Sign out everywhere' from another device must end this one too."""
    _signup(client)
    other_device = CogniSenseClient(base_url="http://testserver", session=transport)
    other_device.login("desk_user", PASSWORD)
    other_device.logout(all_devices=True)

    with pytest.raises(SessionExpired):
        client.risk_report()
    assert not client.logged_in, "a dead token must not be kept and resent"
    assert client.user is None


def test_an_expired_session_raises_session_expired(client, db_factory):
    _signup(client)
    db = db_factory()
    for row in db.query(UserSession).all():
        row.expires_at = row.expires_at.replace(year=2000)
    db.commit()
    db.close()

    with pytest.raises(SessionExpired):
        client.daily_suggestions()


def test_a_wrong_password_is_a_login_error_not_an_expired_session(client):
    _signup(client)
    client.forget()

    with pytest.raises(ApiError) as info:
        client.login("desk_user", "not-the-password")

    assert not isinstance(info.value, SessionExpired)
    assert info.value.status == 401
    assert str(info.value) == "Invalid credentials"


# --------------------------------------------------------------------------
# Logout
# --------------------------------------------------------------------------

def test_logout_revokes_the_token_on_the_server(client, transport):
    _signup(client)
    token = client._token

    client.logout()

    assert not client.logged_in
    r = transport.inner.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, "logout only forgot the token locally"


def test_logout_with_an_already_dead_session_still_signs_out(client, db_factory):
    _signup(client)
    db = db_factory()
    db.query(UserSession).delete()
    db.commit()
    db.close()

    client.logout()          # must not raise
    assert not client.logged_in


# --------------------------------------------------------------------------
# Request and response shapes, end to end
# --------------------------------------------------------------------------

def test_a_full_day_matches_the_api(client):
    _signup(client)
    assert client.morning_today() is None

    morning = client.submit_morning("walk the dog\ncall my sister")
    assert len(morning["presented_associations"]) == 5
    assert client.morning_today()["id"] == morning["id"]

    # The server locks one morning per day and echoes it back.
    with pytest.raises(AlreadySubmitted) as dup:
        client.submit_morning("a second list")
    assert dup.value.existing["id"] == morning["id"]

    midday = client.submit_midday(
        what_user_has_done="walked the dog",
        planned_remainder="",
        response_latency_ms=1500,
        morning_checkin_id=morning["id"],
    )
    assert midday["planned_remainder"] is None, "an empty box is sent as null"

    answers = [
        {"association_id": a["id"], "user_answer": a["object_name"], "response_latency_ms": 1200}
        for a in morning["presented_associations"]
    ]
    evening = client.submit_evening(
        morning_checkin_id=morning["id"],
        recalled_activities="walked the dog and called my sister",
        association_responses=answers,
    )
    assert evening["association_accuracy"] == 1.0
    assert 0 <= evening["daily_cognitive_score"] <= 1

    report = client.risk_report()
    for key in ("user_recent_avg_score", "user_recent_avg_ci_low", "user_recent_avg_ci_high",
                "n_scored_days", "inconclusive", "inconclusive_reason",
                "elevated_concern", "suggestions", "citations", "disclaimer"):
        assert key in report, f"the desktop report reads {key}"
    assert report["inconclusive"] is True, "one day is not a trend"
    assert report["inconclusive_reason"]

    suggestions = client.daily_suggestions()
    assert len(suggestions["suggestions"]) == 3
    assert "Lancet" in suggestions["lancet_risk_factor_source"]


def test_validation_errors_read_as_sentences(client):
    with pytest.raises(ApiError) as info:
        client.signup(
            username="desk_user", password="short", age=70, gender="female",
            race="white", wake_time="07:00:00", sleep_time="22:30:00",
        )
    message = str(info.value)
    assert info.value.status == 422
    assert message.startswith("password:") and "8 characters" in message
    assert "{" not in message and "loc" not in message


def test_describe_covers_every_detail_shape():
    assert describe("Invalid credentials") == "Invalid credentials"
    assert describe({"code": "morning_already_submitted",
                     "message": "Morning check-in already submitted today."}) == (
        "Morning check-in already submitted today."
    )
    assert describe([
        {"loc": ["body", "age"], "msg": "Input should be greater than or equal to 18"},
        {"loc": ["body", "gender"], "msg": "Input should be 'female', 'male'"},
    ]) == (
        "age: Input should be greater than or equal to 18; "
        "gender: Input should be 'female', 'male'"
    )


# --------------------------------------------------------------------------
# The app's own transport, over a real socket
# --------------------------------------------------------------------------

@pytest.fixture()
def live_server(db_factory):
    """The same app, served by uvicorn on an ephemeral port.

    TestClient cannot stand in for the desktop's requests.Session, and the one
    property only that session has -- it refuses cookies -- is the thing that
    keeps the bearer token the sole credential in production.
    """
    uvicorn = pytest.importorskip("uvicorn")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(fastapi_app, lifespan="off", log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.02)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def test_the_desktop_transport_authenticates_by_token_alone(live_server):
    client = CogniSenseClient(base_url=live_server)      # its own requests.Session
    _signup(client, username="socket_user")

    assert len(client._http.cookies) == 0, (
        "the desktop session stored the browser cookie; it would be sent "
        "alongside the token and hide a missing Authorization header"
    )
    assert client.me()["username"] == "socket_user"

    client.logout()
    assert not client.logged_in


def test_an_unreachable_server_is_its_own_error():
    # A port that was free a moment ago: nothing is listening on it.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    client = CogniSenseClient(base_url=f"http://127.0.0.1:{port}")
    with pytest.raises(ServerUnreachable):
        client.login("anyone", "anything")
