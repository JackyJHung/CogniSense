"""Push notifications: quiet hours, cooldown, payload privacy, key stability.

No test here touches the network. `send_to_subscription` is stubbed everywhere,
because a suite that tries to reach Google's push service is slow, flaky, and
fails on a plane.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from app.notifications import scheduler, vapid


# --------------------------------------------------------------------------
# Quiet hours
# --------------------------------------------------------------------------

class FakeUser:
    def __init__(self, wake, sleep, offset_minutes=0):
        self.wake_time = wake
        self.sleep_time = sleep
        self.utc_offset_minutes = offset_minutes


def at(hour, minute=0):
    return datetime(2026, 8, 14, hour, minute, tzinfo=timezone.utc)


def test_awake_within_a_normal_day():
    u = FakeUser(dtime(7, 0), dtime(22, 30))
    assert scheduler.is_awake(u, at(12)) is True
    assert scheduler.is_awake(u, at(7)) is True
    assert scheduler.is_awake(u, at(22, 30)) is True
    assert scheduler.is_awake(u, at(3)) is False
    assert scheduler.is_awake(u, at(23)) is False


def test_sleep_time_past_midnight_is_handled():
    """Wake 07:00, sleep 01:00 - the awake window wraps around midnight."""
    u = FakeUser(dtime(7, 0), dtime(1, 0))
    assert scheduler.is_awake(u, at(12)) is True
    assert scheduler.is_awake(u, at(23)) is True
    assert scheduler.is_awake(u, at(0, 30)) is True
    assert scheduler.is_awake(u, at(3)) is False
    assert scheduler.is_awake(u, at(6)) is False


def test_the_offset_is_what_decides_it():
    """Same UTC instant, two users, opposite answers.

    14:00 UTC is 07:00 for a UTC-7 user (awake) and 02:00 for a UTC+12 user
    (asleep). Without the offset the server would wake somebody at 2am.
    """
    instant = at(14)
    pacific = FakeUser(dtime(7, 0), dtime(22, 0), offset_minutes=-420)   # UTC-7
    nz = FakeUser(dtime(7, 0), dtime(22, 0), offset_minutes=720)         # UTC+12

    assert scheduler.is_awake(pacific, instant) is True
    assert scheduler.is_awake(nz, instant) is False


def test_missing_times_do_not_block_notifications():
    assert scheduler.is_awake(FakeUser(None, None), at(3)) is True


# --------------------------------------------------------------------------
# Payload privacy
# --------------------------------------------------------------------------

def test_payload_never_names_the_items():
    """The notification is a recall prompt, so it must not contain the answers.

    It also lands on a lock screen, where anyone nearby can read it.
    """
    payload = scheduler.build_payload(3)
    blob = " ".join(str(v) for v in payload.values()).lower()

    for leak in ("dentist", "bins", "pills", "prescription", "doctor"):
        assert leak not in blob
    assert "3 things" in payload["body"]
    assert payload["url"] == "/reminders"


def test_payload_singular_reads_correctly():
    assert "1 thing saved" in scheduler.build_payload(1)["body"]
    assert "2 things saved" in scheduler.build_payload(2)["body"]


# --------------------------------------------------------------------------
# VAPID keys
# --------------------------------------------------------------------------

def test_keypair_is_stable_across_calls(tmp_path, monkeypatch):
    """Regenerating the key would silently break every existing subscription."""
    monkeypatch.setattr(vapid, "KEY_DIR", tmp_path)
    monkeypatch.setattr(vapid, "PRIVATE_KEY_PATH", tmp_path / "vapid_private.pem")

    first = vapid.public_key_b64()
    second = vapid.public_key_b64()
    assert first == second
    assert (tmp_path / "vapid_private.pem").exists()


def test_public_key_is_an_uncompressed_p256_point(tmp_path, monkeypatch):
    """PushManager.subscribe rejects anything else."""
    import base64

    monkeypatch.setattr(vapid, "KEY_DIR", tmp_path)
    monkeypatch.setattr(vapid, "PRIVATE_KEY_PATH", tmp_path / "vapid_private.pem")

    key = vapid.public_key_b64()
    assert "=" not in key, "must be unpadded base64url"
    assert "+" not in key and "/" not in key, "must be url-safe alphabet"

    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    assert len(raw) == 65
    assert raw[0] == 0x04


# --------------------------------------------------------------------------
# The scheduler tick
# --------------------------------------------------------------------------

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import create_session  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.push import PushSubscription  # noqa: E402
from app.models.reminder import STATUS_PENDING, ReminderItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.notifications import sender  # noqa: E402
from app.routes import push as push_routes  # noqa: E402


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import checkin, image_association, push, reminder, user  # noqa: F401
    Base.metadata.create_all(bind=engine)

    session = Session()
    user = User(
        id=1, username="pusher", hashed_password="x", age=70, gender="female",
        race="white", wake_time=dtime(7), sleep_time=dtime(22),
        utc_offset_minutes=0,
    )
    session.add(user)
    session.add(PushSubscription(
        user_id=1, endpoint="https://push.example/abc", p256dh="k", auth="a",
    ))
    session.commit()
    session.auth_token = create_session(session, user)  # type: ignore[attr-defined]

    sent: list[dict] = []

    def fake_send(subscription_info, payload, ttl=None):
        sent.append(payload)
        return sender.SendResult(ok=True, status=201)

    monkeypatch.setattr(sender, "send_to_subscription", fake_send)
    session.sent = sent  # type: ignore[attr-defined]
    yield session
    session.close()


def _add_reminder(db, due_at=None):
    db.add(ReminderItem(user_id=1, description="call the dentist",
                        status=STATUS_PENDING, due_at=due_at))
    db.commit()


def test_tick_pushes_when_something_is_due(db):
    _add_reminder(db)
    summary = scheduler.run_tick(db, now_utc=at(12))

    assert summary["pushed"] == 1
    assert len(db.sent) == 1
    assert db.query(User).get(1).last_push_at is not None


def test_tick_is_silent_when_nothing_is_pending(db):
    summary = scheduler.run_tick(db, now_utc=at(12))
    assert summary["pushed"] == 0
    assert summary["nothing_due"] == 1
    assert db.sent == []


def test_tick_respects_quiet_hours(db):
    _add_reminder(db)
    summary = scheduler.run_tick(db, now_utc=at(3))   # 03:00, user sleeps 22:00-07:00

    assert summary["asleep"] == 1
    assert summary["pushed"] == 0
    assert db.sent == []


def test_tick_respects_the_cooldown(db):
    _add_reminder(db)

    first = scheduler.run_tick(db, now_utc=at(8))
    assert first["pushed"] == 1

    # One hour later, well inside the 6h cooldown.
    second = scheduler.run_tick(db, now_utc=at(9))
    assert second["cooling_down"] == 1
    assert second["pushed"] == 0
    assert len(db.sent) == 1

    # After the cooldown has elapsed it fires again.
    third = scheduler.run_tick(db, now_utc=at(8) + timedelta(hours=7))
    assert third["pushed"] == 1
    assert len(db.sent) == 2


def test_future_due_dates_do_not_trigger(db):
    _add_reminder(db, due_at=datetime(2026, 8, 14, 20, 0))   # naive UTC, later today
    summary = scheduler.run_tick(db, now_utc=at(12))
    assert summary["nothing_due"] == 1
    assert db.sent == []


def test_a_past_due_date_does_trigger(db):
    _add_reminder(db, due_at=datetime(2026, 8, 14, 9, 0))
    summary = scheduler.run_tick(db, now_utc=at(12))
    assert summary["pushed"] == 1


def test_dead_subscriptions_are_pruned(db, monkeypatch):
    _add_reminder(db)

    def gone(subscription_info, payload, ttl=None):
        return sender.SendResult(ok=False, status=410, gone=True, error="gone")

    monkeypatch.setattr(sender, "send_to_subscription", gone)
    scheduler.run_tick(db, now_utc=at(12))

    assert db.query(PushSubscription).count() == 0, (
        "a 410 means the endpoint is dead forever and must not be retried"
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(push_routes.router)

    # Must be a generator FUNCTION -- FastAPI inspects the callable to decide
    # whether to drive the yield protocol. A lambda returning an iterator is
    # handed to the endpoint as-is, and the route gets an iterator where it
    # expects a Session.
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {db.auth_token}"
        yield c


def test_subscribe_is_idempotent_on_the_endpoint(client, db):
    body = {
        "user_id": 1,
        "subscription": {
            "endpoint": "https://push.example/second",
            "keys": {"p256dh": "kk", "auth": "aa"},
        },
        "utc_offset_minutes": -420,
    }
    first = client.post("/push/subscribe", json=body)
    assert first.status_code == 201, first.text

    second = client.post("/push/subscribe", json=body)
    assert second.status_code == 201, "re-subscribing must update, not 500"

    assert db.query(PushSubscription).filter(
        PushSubscription.endpoint == "https://push.example/second"
    ).count() == 1
    # The browser's offset is recorded so quiet hours mean something.
    assert db.query(User).get(1).utc_offset_minutes == -420


def test_status_reports_the_chain(client):
    r = client.get("/push/status/1")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["devices"] == 1
    assert "quiet between" in body["quiet_hours"]


def test_test_push_reports_no_devices(client, db):
    db.query(PushSubscription).delete()
    db.commit()
    r = client.post("/push/test/1")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_devices"


def test_test_push_does_not_consume_the_cooldown(client, db):
    """Pressing 'send a test' must not suppress the next real reminder."""
    r = client.post("/push/test/1")
    assert r.status_code == 200
    assert r.json()["sent"] == 1
    assert db.query(User).get(1).last_push_at is None


def test_unsubscribe_is_forgiving(client):
    r = client.post("/push/unsubscribe", json={"endpoint": "https://push.example/never"})
    assert r.status_code == 200
    assert r.json()["removed"] == 0
