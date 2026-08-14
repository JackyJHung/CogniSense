"""The morning-check-in day window must line up with what SQLite stores.

REGRESSION. `_today_bounds()` used to build its window from `date.today()` --
the server's LOCAL date -- and compare it against `timestamp` columns that
SQLite fills from `func.now()` in UTC. Whenever the local date and the UTC date
disagreed, the window pointed at the wrong day, and two things broke silently:

  1. the duplicate-morning guard stopped firing, so a user could roll a second
     set of image associations and have the evening test graded against the
     wrong morning -- exactly what the 409 exists to prevent
  2. GET /checkins/morning/today/{user_id} 404'd on a check-in that existed

On a UTC-7 machine that was every evening from 17:00 local onward, i.e. seven
hours a day. These tests are written against injected instants so they fail on
a broken window at any wall-clock time, in any server timezone.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.checkins import _today_bounds


def _contains(bounds: tuple[datetime, datetime], instant_utc: datetime) -> bool:
    start, end = bounds
    naive = instant_utc.astimezone(timezone.utc).replace(tzinfo=None)
    return start <= naive < end


def test_window_contains_its_own_instant_across_a_full_day():
    """The invariant: the window for instant T always contains T."""
    base = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    for hour in range(48):          # two full days, hour by hour
        instant = base + timedelta(hours=hour)
        assert _contains(_today_bounds(instant), instant), (
            f"window for {instant.isoformat()} does not contain it"
        )


def test_the_evening_case_that_used_to_break():
    """18:00 local on a UTC-7 machine is 01:00 UTC the NEXT day.

    A check-in submitted then stores 2026-08-15T01:00 UTC. A window built from
    the local date (Aug 14) would be [Aug 14 00:00, Aug 15 00:00) and would miss
    it by an hour.
    """
    instant = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)   # = Aug 14 18:00 at UTC-7
    start, end = _today_bounds(instant)

    assert start == datetime(2026, 8, 15, 0, 0)
    assert end == datetime(2026, 8, 16, 0, 0)
    assert _contains((start, end), instant)

    stale_local_window = (datetime(2026, 8, 14, 0, 0), datetime(2026, 8, 15, 0, 0))
    assert not _contains(stale_local_window, instant), (
        "sanity check: the old local-date window really did miss this instant"
    )


def test_bounds_are_naive_to_match_sqlite():
    """SQLite returns naive datetimes; the comparison must be like-for-like."""
    start, end = _today_bounds(datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc))
    assert start.tzinfo is None
    assert end.tzinfo is None
    assert end - start == timedelta(days=1)


def test_naive_input_is_treated_as_utc():
    start, end = _today_bounds(datetime(2026, 8, 15, 1, 0))
    assert start == datetime(2026, 8, 15, 0, 0)
    assert end == datetime(2026, 8, 16, 0, 0)


def test_default_window_contains_now():
    """No-argument call must still bracket the current instant."""
    now = datetime.now(timezone.utc)
    assert _contains(_today_bounds(), now)


# --------------------------------------------------------------------------
# End-to-end: the guard the window protects
# --------------------------------------------------------------------------

pytest.importorskip("fastapi", reason="fastapi not installed in this interpreter")
pytest.importorskip("httpx", reason="httpx is required by fastapi's TestClient")

from datetime import time as dtime  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import create_session  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes import checkins  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import checkin, image_association, reminder, user  # noqa: F401
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    s = TestingSession()
    user = User(id=1, username="tz", hashed_password="x", age=70, gender="female",
                race="white", wake_time=dtime(7), sleep_time=dtime(22))
    s.add(user)
    s.commit()
    token = create_session(s, user)
    s.close()

    app = FastAPI()
    app.include_router(checkins.router)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def test_second_morning_checkin_is_rejected(client):
    payload = {"user_id": 1, "planned_activities": "walk the dog, buy milk"}

    first = client.post("/checkins/morning", json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/checkins/morning", json=payload)
    assert second.status_code == 409, (
        "the duplicate-morning guard did not fire; the day window is not "
        "finding the check-in that was just written"
    )
    assert second.json()["detail"]["code"] == "morning_already_submitted"
    # The existing record is echoed so the client need not re-fetch.
    assert second.json()["detail"]["existing"]["id"] == first.json()["id"]


def test_todays_morning_is_retrievable_right_after_creation(client):
    created = client.post(
        "/checkins/morning", json={"user_id": 1, "planned_activities": "call sister"},
    )
    assert created.status_code == 201

    fetched = client.get("/checkins/morning/today/1")
    assert fetched.status_code == 200, (
        "a check-in written moments ago was not found in today's window"
    )
    assert fetched.json()["id"] == created.json()["id"]
