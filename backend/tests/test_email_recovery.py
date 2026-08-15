"""Email-based account recovery: verification, reset links, and non-disclosure.

Two properties carry most of the weight here:

  test_an_unverified_address_cannot_reset_the_account
      An unverified address is worse than no address. A typo at signup would
      send reset links to a stranger's inbox, and recovery becomes takeover.

  test_forgot_says_the_same_thing_whatever_happens
      Whether an account exists, has an email, or has verified it must not be
      observable. On a cognitive-health app, confirming that an address has an
      account is itself a disclosure.

No SMTP anywhere: `app.emailer.send_email` is stubbed, and the tokens are read
out of the database rather than out of a message.
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

from app import config, ratelimit  # noqa: E402
from app.csrf import CSRF_COOKIE, SESSION_COOKIE  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.security import EmailToken  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes import recovery as recovery_route  # noqa: E402
from app.routes.users import pwd_context  # noqa: E402

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "an-entirely-different-one"
ADDRESS = "alice@example.com"


@pytest.fixture()
def env(monkeypatch):
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
    db.add(User(id=2, username="bob", hashed_password=pwd_context.hash(PASSWORD),
                age=72, gender="male", race="white",
                wake_time=dtime(7), sleep_time=dtime(22)))
    db.commit()

    # Capture instead of send. Nothing here touches a mail server.
    sent: list[dict] = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr("app.emailer.send_email", fake_send)

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        yield client, db, sent
    fastapi_app.dependency_overrides.clear()
    db.close()


def login(client, username="alice", password=PASSWORD):
    return client.post("/users/login", json={"username": username, "password": password})


def csrf(client):
    token = client.cookies.get(CSRF_COOKIE)
    return {"X-CSRF-Token": token} if token else {}


def token_for(db, user_id, purpose):
    """Read the raw token's HASH row; tests re-mint rather than un-hash."""
    return (
        db.query(EmailToken)
        .filter(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
        .filter(EmailToken.used_at.is_(None))
        .first()
    )


def add_email(client, address=ADDRESS):
    return client.post("/recovery/email", headers=csrf(client),
                       json={"current_password": PASSWORD, "email": address})


def raw_token(monkeypatch_target: list) -> str:
    """The last token issued, captured from the outgoing message body."""
    body = monkeypatch_target[-1]["body"]
    return body.split("token=")[1].split()[0].strip()


# --------------------------------------------------------------------------
# Adding and verifying an address
# --------------------------------------------------------------------------

def test_adding_an_email_sends_a_confirmation(env):
    client, db, sent = env
    login(client)
    r = add_email(client)

    assert r.status_code == 200
    assert ADDRESS in r.json()["message"]
    assert len(sent) == 1
    assert sent[0]["to"] == ADDRESS
    assert "confirm" in sent[0]["subject"].lower()
    assert "/verify-email?token=" in sent[0]["body"]


def test_adding_an_email_requires_the_password(env):
    """A borrowed session must not be able to redirect recovery elsewhere."""
    client, _, sent = env
    login(client)
    r = client.post("/recovery/email", headers=csrf(client),
                    json={"current_password": "wrong", "email": ADDRESS})
    assert r.status_code == 401
    assert sent == []


def test_the_address_starts_unverified(env):
    client, db, _ = env
    login(client)
    add_email(client)
    db.expire_all()
    assert db.query(User).get(1).email == ADDRESS
    assert db.query(User).get(1).email_is_verified is False


def test_the_confirmation_link_verifies_it(env):
    client, db, sent = env
    login(client)
    add_email(client)

    r = client.post("/recovery/email/verify", json={"token": raw_token(sent)})
    assert r.status_code == 200

    db.expire_all()
    assert db.query(User).get(1).email_is_verified is True


def test_a_confirmation_link_works_only_once(env):
    client, _, sent = env
    login(client)
    add_email(client)
    token = raw_token(sent)

    assert client.post("/recovery/email/verify", json={"token": token}).status_code == 200
    assert client.post("/recovery/email/verify", json={"token": token}).status_code == 400


def test_changing_the_address_drops_verification(env):
    client, db, sent = env
    login(client)
    add_email(client)
    client.post("/recovery/email/verify", json={"token": raw_token(sent)})

    add_email(client, "alice-new@example.com")
    db.expire_all()
    user = db.query(User).get(1)
    assert user.email == "alice-new@example.com"
    assert user.email_is_verified is False, "a new address must be re-confirmed"


def test_two_accounts_cannot_share_an_address(env):
    client, _, _ = env
    login(client)
    add_email(client)
    client.post("/users/logout", headers=csrf(client))
    client.cookies.clear()

    login(client, "bob")
    r = add_email(client)
    assert r.status_code == 409
    # Generic: it must not confirm that the address is registered elsewhere.
    assert "example.com" not in r.json()["detail"]


# --------------------------------------------------------------------------
# The reset link
# --------------------------------------------------------------------------

def _verified_email(client, sent):
    login(client)
    add_email(client)
    client.post("/recovery/email/verify", json={"token": raw_token(sent)})
    client.post("/users/logout", headers=csrf(client))
    client.cookies.clear()


def test_a_reset_link_changes_the_password(env):
    client, _, sent = env
    _verified_email(client, sent)

    r = client.post("/recovery/forgot", json={"identifier": "alice"})
    assert r.status_code == 200
    assert "reset" in sent[-1]["subject"].lower()

    reset = client.post("/recovery/reset-token", json={
        "token": raw_token(sent), "new_password": NEW_PASSWORD})
    assert reset.status_code == 200

    client.cookies.clear()
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_the_email_address_also_works_as_the_identifier(env):
    client, _, sent = env
    _verified_email(client, sent)
    client.post("/recovery/forgot", json={"identifier": ADDRESS})
    assert sent[-1]["to"] == ADDRESS


def test_an_unverified_address_cannot_reset_the_account(env):
    """The takeover vector this design exists to close.

    A mistyped address at signup would otherwise receive a working reset link.
    """
    client, _, sent = env
    login(client)
    add_email(client)          # deliberately NOT verified
    client.post("/users/logout", headers=csrf(client))
    client.cookies.clear()
    before = len(sent)

    r = client.post("/recovery/forgot", json={"identifier": "alice"})
    assert r.status_code == 200, "still a generic success, to avoid disclosure"
    assert len(sent) == before, "but no reset link is actually sent"


def test_a_reset_link_works_only_once(env):
    client, _, sent = env
    _verified_email(client, sent)
    client.post("/recovery/forgot", json={"identifier": "alice"})
    token = raw_token(sent)

    assert client.post("/recovery/reset-token", json={
        "token": token, "new_password": NEW_PASSWORD}).status_code == 200
    assert client.post("/recovery/reset-token", json={
        "token": token, "new_password": "third-password-here"}).status_code == 400


def test_an_expired_reset_link_is_refused(env):
    client, db, sent = env
    _verified_email(client, sent)
    client.post("/recovery/forgot", json={"identifier": "alice"})
    token = raw_token(sent)

    row = token_for(db, 1, EmailToken.PURPOSE_RESET)
    row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    db.commit()

    assert client.post("/recovery/reset-token", json={
        "token": token, "new_password": NEW_PASSWORD}).status_code == 400


def test_requesting_again_invalidates_the_previous_link(env):
    """Clicking 'email me a link' three times must leave one live link, not three."""
    client, _, sent = env
    _verified_email(client, sent)

    client.post("/recovery/forgot", json={"identifier": "alice"})
    first = raw_token(sent)
    client.post("/recovery/forgot", json={"identifier": "alice"})
    second = raw_token(sent)

    assert client.post("/recovery/reset-token", json={
        "token": first, "new_password": NEW_PASSWORD}).status_code == 400
    assert client.post("/recovery/reset-token", json={
        "token": second, "new_password": NEW_PASSWORD}).status_code == 200


def test_a_link_dies_if_the_address_changes(env):
    """A link mailed to an old inbox must not stay live after moving away."""
    client, db, sent = env
    _verified_email(client, sent)
    client.post("/recovery/forgot", json={"identifier": "alice"})
    token = raw_token(sent)

    login(client)
    add_email(client, "alice-moved@example.com")
    client.cookies.clear()

    assert client.post("/recovery/reset-token", json={
        "token": token, "new_password": NEW_PASSWORD}).status_code == 400


def test_a_verification_token_cannot_be_used_as_a_reset(env):
    """Purposes are not interchangeable."""
    client, _, sent = env
    login(client)
    add_email(client)
    verification = raw_token(sent)

    assert client.post("/recovery/reset-token", json={
        "token": verification, "new_password": NEW_PASSWORD}).status_code == 400


def test_a_reset_revokes_every_session(env):
    """Whoever held a session before the reset must lose it.

    The reset issues a FRESH session on its response, and TestClient's cookie
    jar adopts it immediately -- so the old session has to be captured first and
    replayed explicitly, or this just re-checks the new one.
    """
    client, db, sent = env
    _verified_email(client, sent)
    login(client)

    stolen = client.cookies.get(SESSION_COOKIE)
    assert stolen, "expected a session cookie to have been set"

    client.post("/recovery/forgot", json={"identifier": "alice"})
    client.post("/recovery/reset-token", json={
        "token": raw_token(sent), "new_password": NEW_PASSWORD})

    client.cookies.clear()
    replayed = client.get("/users/me", cookies={SESSION_COOKIE: stolen})
    assert replayed.status_code == 401, "the pre-reset session should be dead"


# --------------------------------------------------------------------------
# Non-disclosure
# --------------------------------------------------------------------------

def test_forgot_says_the_same_thing_whatever_happens(env):
    client, _, sent = env
    _verified_email(client, sent)

    real = client.post("/recovery/forgot", json={"identifier": "alice"})
    missing = client.post("/recovery/forgot", json={"identifier": "nobody-at-all"})
    no_email = client.post("/recovery/forgot", json={"identifier": "bob"})

    assert real.status_code == missing.status_code == no_email.status_code == 200
    assert real.json() == missing.json() == no_email.json()


def test_forgot_is_throttled(env):
    """Otherwise it is a free, unlimited probe for which accounts exist."""
    client, _, _ = env
    for _ in range(ratelimit.USER_MAX_FAILURES + 1):
        client.post("/recovery/forgot", json={"identifier": "nobody-at-all"})

    blocked = client.post("/recovery/forgot", json={"identifier": "nobody-at-all"})
    assert blocked.status_code == 429


def test_status_reports_the_email_state(env):
    client, _, sent = env
    login(client)

    before = client.get("/recovery/status").json()
    assert before["email"] is None and before["email_verified"] is False

    add_email(client)
    unverified = client.get("/recovery/status").json()
    assert unverified["email"] == ADDRESS and unverified["email_verified"] is False

    client.post("/recovery/email/verify", json={"token": raw_token(sent)})
    verified = client.get("/recovery/status").json()
    assert verified["email_verified"] is True


def test_status_says_whether_mail_is_actually_being_sent(env, monkeypatch):
    """So the UI never tells somebody to check an inbox that will stay empty."""
    client, _, _ = env
    login(client)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    assert client.get("/recovery/status").json()["email_delivery_enabled"] is False


def test_offline_codes_still_work_alongside_email(env):
    """Adding email must not break the code path for users who never set one."""
    client, _, _ = env
    login(client)
    codes = client.post("/recovery/codes", headers=csrf(client)).json()["codes"]
    client.cookies.clear()

    r = client.post("/recovery/reset", json={
        "username": "alice", "code": codes[0], "new_password": NEW_PASSWORD})
    assert r.status_code == 200
