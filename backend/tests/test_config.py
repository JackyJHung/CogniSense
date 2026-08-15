"""Configuration validation, proxy trust, and session idle expiry.

The important test here is `test_forwarded_for_is_ignored_from_an_untrusted_peer`.
X-Forwarded-For used to be believed whenever it was present, and since any
client can set a header, sending a different value on each request bought a
fresh per-IP rate-limit budget every time. The address limit -- the one that
stops a single host spraying one guess across many accounts -- was decorative.
"""
from __future__ import annotations

import importlib
from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from app import config, ratelimit


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    """Enough of starlette.Request for client_ip()."""

    def __init__(self, peer, headers=None):
        self.client = FakeClient(peer)
        self.headers = headers or {}


# --------------------------------------------------------------------------
# Proxy trust
# --------------------------------------------------------------------------

def test_forwarded_for_is_ignored_from_an_untrusted_peer(monkeypatch):
    """The spoofing fix, stated directly.

    With no trusted proxies configured -- the default -- the header must be
    ignored entirely and the socket address used instead. Otherwise an attacker
    rotates the header and never trips the per-IP limit.
    """
    monkeypatch.setattr(config, "TRUSTED_PROXIES", set())
    request = FakeRequest("203.0.113.9", {"x-forwarded-for": "1.2.3.4"})
    assert ratelimit.client_ip(request) == "203.0.113.9"


def test_a_rotating_forged_header_does_not_buy_a_fresh_budget(monkeypatch):
    """Same attacker, 50 different forged headers, still one throttle key."""
    monkeypatch.setattr(config, "TRUSTED_PROXIES", set())
    seen = {
        ratelimit.client_ip(
            FakeRequest("203.0.113.9", {"x-forwarded-for": f"10.0.0.{i}"})
        )
        for i in range(50)
    }
    assert seen == {"203.0.113.9"}


def test_forwarded_for_is_honoured_from_a_trusted_proxy(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", {"127.0.0.1"})
    request = FakeRequest("127.0.0.1", {"x-forwarded-for": "198.51.100.7"})
    assert ratelimit.client_ip(request) == "198.51.100.7"


def test_the_leftmost_forwarded_entry_is_the_client(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", {"127.0.0.1"})
    request = FakeRequest(
        "127.0.0.1", {"x-forwarded-for": "198.51.100.7, 10.0.0.1, 10.0.0.2"}
    )
    assert ratelimit.client_ip(request) == "198.51.100.7"


def test_a_trusted_proxy_without_the_header_falls_back_to_the_peer(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", {"127.0.0.1"})
    assert ratelimit.client_ip(FakeRequest("127.0.0.1")) == "127.0.0.1"


def test_missing_request_does_not_explode():
    assert ratelimit.client_ip(None) == "unknown"


# --------------------------------------------------------------------------
# Startup validation
# --------------------------------------------------------------------------

def _reloaded(monkeypatch, **env):
    """Re-import config with a given environment."""
    for key in list(env):
        monkeypatch.setenv(key, env[key])
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_config():
    """Any test that reloads config must leave the real one behind it."""
    yield
    importlib.reload(config)


def test_development_is_permissive(monkeypatch):
    cfg = _reloaded(monkeypatch, COGNISENSE_ENV="development")
    assert cfg.problems() == []
    cfg.validate()  # must not raise


def test_production_rejects_insecure_cookies(monkeypatch):
    cfg = _reloaded(
        monkeypatch,
        COGNISENSE_ENV="production",
        COGNISENSE_COOKIE_SECURE="0",
        COGNISENSE_ALLOWED_ORIGINS="https://cognisense.example",
        COGNISENSE_VAPID_SUBJECT="mailto:real@example.com",
    )
    assert any("COOKIE_SECURE" in p for p in cfg.problems())
    with pytest.raises(cfg.ConfigError):
        cfg.validate()


def test_production_rejects_empty_origins(monkeypatch):
    cfg = _reloaded(
        monkeypatch,
        COGNISENSE_ENV="production",
        COGNISENSE_COOKIE_SECURE="1",
        COGNISENSE_ALLOWED_ORIGINS="",
        COGNISENSE_VAPID_SUBJECT="mailto:real@example.com",
    )
    assert any("ALLOWED_ORIGINS is empty" in p for p in cfg.problems())


def test_production_rejects_leftover_development_origins(monkeypatch):
    """The realistic deploy mistake: shipping with the dev origins still set."""
    cfg = _reloaded(
        monkeypatch,
        COGNISENSE_ENV="production",
        COGNISENSE_COOKIE_SECURE="1",
        COGNISENSE_ALLOWED_ORIGINS="https://cognisense.example,http://localhost:5173",
        COGNISENSE_VAPID_SUBJECT="mailto:real@example.com",
    )
    found = " ".join(cfg.problems())
    assert "localhost" in found
    assert "plain-http" in found


def test_production_rejects_the_placeholder_vapid_subject(monkeypatch):
    cfg = _reloaded(
        monkeypatch,
        COGNISENSE_ENV="production",
        COGNISENSE_COOKIE_SECURE="1",
        COGNISENSE_ALLOWED_ORIGINS="https://cognisense.example",
    )
    assert any("VAPID_SUBJECT" in p for p in cfg.problems())


def test_a_correct_production_config_passes(monkeypatch):
    cfg = _reloaded(
        monkeypatch,
        COGNISENSE_ENV="production",
        COGNISENSE_COOKIE_SECURE="1",
        COGNISENSE_ALLOWED_ORIGINS="https://cognisense.example",
        COGNISENSE_VAPID_SUBJECT="mailto:ops@example.com",
    )
    assert cfg.problems() == []
    cfg.validate()


def test_production_defaults_cookie_secure_on(monkeypatch):
    """Forgetting the flag entirely must not silently produce insecure cookies."""
    monkeypatch.delenv("COGNISENSE_COOKIE_SECURE", raising=False)
    cfg = _reloaded(monkeypatch, COGNISENSE_ENV="production")
    assert cfg.COOKIE_SECURE is True


def test_trusted_proxies_default_to_none(monkeypatch):
    monkeypatch.delenv("COGNISENSE_TRUSTED_PROXIES", raising=False)
    cfg = _reloaded(monkeypatch, COGNISENSE_ENV="production")
    assert cfg.TRUSTED_PROXIES == set(), "the safe default is to trust no proxy"


def test_a_nonsense_integer_falls_back_rather_than_crashing(monkeypatch):
    cfg = _reloaded(monkeypatch, COGNISENSE_SESSION_IDLE_DAYS="not-a-number")
    assert cfg.SESSION_IDLE_DAYS == 7


# --------------------------------------------------------------------------
# Session idle expiry
# --------------------------------------------------------------------------

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import auth  # noqa: E402
from app.auth import create_session, hash_token  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from app.models.user import User  # noqa: E402


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
    db.add(User(id=1, username="idle", hashed_password="x", age=70, gender="female",
                race="white", wake_time=dtime(7), sleep_time=dtime(22)))
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


def test_an_idle_session_expires(env):
    """A session left untouched on a lost device must stop working.

    Absolute expiry alone would keep this valid for another three weeks.
    """
    client, db = env
    token = create_session(db, db.query(User).get(1))
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    row = db.query(UserSession).filter(UserSession.token_hash == hash_token(token)).first()
    row.last_used_at = datetime.now(timezone.utc) - timedelta(
        days=auth.SESSION_IDLE_DAYS + 1
    )
    db.commit()

    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_an_idle_session_is_deleted_not_just_refused(env):
    client, db = env
    token = create_session(db, db.query(User).get(1))
    row = db.query(UserSession).filter(UserSession.token_hash == hash_token(token)).first()
    row.last_used_at = datetime.now(timezone.utc) - timedelta(
        days=auth.SESSION_IDLE_DAYS + 1
    )
    db.commit()

    client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    db.expire_all()
    assert db.query(UserSession).filter(
        UserSession.token_hash == hash_token(token)
    ).first() is None


def test_active_use_keeps_a_session_alive(env):
    """Idle expiry must not log out somebody who is actually using the app."""
    client, db = env
    token = create_session(db, db.query(User).get(1))
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(3):
        assert client.get("/users/me", headers=headers).status_code == 200

    row = db.query(UserSession).filter(UserSession.token_hash == hash_token(token)).first()
    db.refresh(row)
    assert row.last_used_at is not None, "each request should refresh the idle clock"


def test_a_never_used_session_still_ages_out(env):
    """last_used_at is null until the first request; created_at is the fallback."""
    client, db = env
    token = create_session(db, db.query(User).get(1))
    row = db.query(UserSession).filter(UserSession.token_hash == hash_token(token)).first()
    assert row.last_used_at is None
    row.created_at = datetime.now(timezone.utc) - timedelta(
        days=auth.SESSION_IDLE_DAYS + 1
    )
    db.commit()

    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
