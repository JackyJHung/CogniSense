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

THE SECOND HALF. That fix made the day a UTC day -- consistent, but for a user
in Los Angeles it still ended at 17:00 local, so an evening check-in was filed
under tomorrow. The day is now the user's own, from their IANA zone, and the
tests at the bottom pin it: evening and morning share a day, local midnight
starts a new one, and the two DST days are 23 and 25 hours long. The tests
above still hold unchanged -- with no zone given, the day is a UTC day.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import timezones
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
# The user's own day
# --------------------------------------------------------------------------

LA = ZoneInfo("America/Los_Angeles")


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_an_evening_in_los_angeles_is_the_same_local_day():
    """08:00 and 18:00 on 14 August in Los Angeles: one day, one window.

    In UTC those are 15:00 on the 14th and 01:00 on the 15th -- two UTC dates,
    which is exactly how the UTC day used to split them.
    """
    morning = _utc(2026, 8, 14, 15)      # 08:00 PDT
    evening = _utc(2026, 8, 15, 1)       # 18:00 PDT
    window = _today_bounds(evening, LA)

    assert window == (datetime(2026, 8, 14, 7), datetime(2026, 8, 15, 7))
    assert _contains(window, morning) and _contains(window, evening)
    assert not _contains(_today_bounds(evening), morning), (
        "sanity check: a UTC day really does put these on different days"
    )


def test_just_after_local_midnight_is_a_new_day():
    before = _utc(2026, 8, 15, 6, 59)    # 23:59 PDT on the 14th
    after = _utc(2026, 8, 15, 7, 1)      # 00:01 PDT on the 15th

    assert _today_bounds(after, LA)[0] == datetime(2026, 8, 15, 7), "starts at local midnight"
    assert not _contains(_today_bounds(after, LA), before)
    assert not _contains(_today_bounds(before, LA), after)


def test_the_spring_forward_day_is_23_hours():
    """8 March 2026: at 02:00 PST the clocks jump to 03:00 PDT."""
    start, end = _today_bounds(_utc(2026, 3, 8, 20), LA)        # noon PDT

    assert start == datetime(2026, 3, 8, 8)       # 00:00 PST
    assert end == datetime(2026, 3, 9, 7)         # 00:00 PDT
    assert end - start == timedelta(hours=23)
    assert _contains((start, end), _utc(2026, 3, 8, 9, 30))     # 01:30 PST
    assert _contains((start, end), _utc(2026, 3, 8, 10, 30))    # 03:30 PDT


def test_the_fall_back_day_is_25_hours():
    """1 November 2026: 01:00-02:00 happens twice, once in PDT, once in PST."""
    start, end = _today_bounds(_utc(2026, 11, 1, 20), LA)       # noon PST

    assert start == datetime(2026, 11, 1, 7)      # 00:00 PDT
    assert end == datetime(2026, 11, 2, 8)        # 00:00 PST
    assert end - start == timedelta(hours=25)
    assert _contains((start, end), _utc(2026, 11, 1, 8, 30))    # 01:30 PDT, first time
    assert _contains((start, end), _utc(2026, 11, 1, 9, 30))    # 01:30 PST, second time


def test_every_instant_across_both_dst_weekends_is_in_its_own_window():
    for first in (_utc(2026, 3, 7, 0), _utc(2026, 10, 31, 0)):
        for step in range(4 * 72):                              # 72h, every 15 minutes
            instant = first + timedelta(minutes=15 * step)
            start, end = _today_bounds(instant, LA)
            assert _contains((start, end), instant), instant.isoformat()
            assert end - start in (timedelta(hours=23), timedelta(hours=24),
                                   timedelta(hours=25))


def test_unknown_zone_names_are_rejected():
    for bad in ("Mars/Olympus_Mons", "", "localtime", "../../etc/passwd",
                "America/Los_Angeles ", "Etc/Unknown", "x" * 200):
        assert not timezones.is_valid(bad), bad
        with pytest.raises(ValueError):
            timezones.validate(bad)
    # Real names, including the legacy aliases some browsers still report.
    for good in ("America/Los_Angeles", "UTC", "Europe/London", "Asia/Calcutta"):
        assert timezones.validate(good) == good


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
        c.db_factory = TestingSession   # lets a test set the zone and plant rows
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


# --------------------------------------------------------------------------
# End-to-end: the user's own day, with the clock pinned
# --------------------------------------------------------------------------

from app.models.checkin import MorningCheckin  # noqa: E402


def _set_zone(client, zone):
    s = client.db_factory()
    s.get(User, 1).timezone = zone
    s.commit()
    s.close()


def _morning_at(client, naive_utc):
    s = client.db_factory()
    m = MorningCheckin(user_id=1, timestamp=naive_utc, planned_activities="walk the dog",
                       presented_associations=[])
    s.add(m)
    s.commit()
    morning_id = m.id
    s.close()
    return morning_id


def test_at_1800_in_los_angeles_this_mornings_checkin_is_found(client, monkeypatch):
    """What a Los Angeles user saw: after 17:00 local, today's morning 'vanished'."""
    morning_id = _morning_at(client, datetime(2026, 8, 14, 15))            # 08:00 PDT
    monkeypatch.setattr(checkins, "_now", lambda: _utc(2026, 8, 15, 1))    # 18:00 PDT

    _set_zone(client, None)          # the old behaviour: a UTC day
    assert client.get("/checkins/morning/today/1").status_code == 404

    _set_zone(client, "America/Los_Angeles")
    found = client.get("/checkins/morning/today/1")
    assert found.status_code == 200, found.text
    assert found.json()["id"] == morning_id

    again = client.post("/checkins/morning", json={"user_id": 1, "planned_activities": "again"})
    assert again.status_code == 409, "a second morning on the same local day must be refused"


def test_just_after_local_midnight_a_new_morning_is_allowed(client, monkeypatch):
    _set_zone(client, "America/Los_Angeles")
    _morning_at(client, datetime(2026, 8, 14, 15))                         # 08:00 PDT, the 14th
    monkeypatch.setattr(checkins, "_now", lambda: _utc(2026, 8, 15, 7, 1)) # 00:01 PDT, the 15th

    assert client.get("/checkins/morning/today/1").status_code == 404
    fresh = client.post("/checkins/morning", json={"user_id": 1, "planned_activities": "new day"})
    assert fresh.status_code == 201, fresh.text


# --------------------------------------------------------------------------
# Where the zone comes from: signup, login, settings
# --------------------------------------------------------------------------

from app.main import app as fastapi_app  # noqa: E402

SIGNUP = {
    "username": "zoned", "password": "correct-horse-battery", "age": 70,
    "gender": "female", "race": "white", "wake_time": "07:00:00", "sleep_time": "22:00:00",
}
CREDS = {"username": SIGNUP["username"], "password": SIGNUP["password"]}


@pytest.fixture()
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.models import (  # noqa: F401
        checkin, image_association, push, reminder, security, session as _s, user,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def test_signup_records_the_devices_zone(api):
    r = api.post("/users/signup", json={**SIGNUP, "timezone": "America/Los_Angeles"})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["timezone"] == "America/Los_Angeles"


def test_signup_rejects_an_unknown_zone(api):
    r = api.post("/users/signup", json={**SIGNUP, "timezone": "Mars/Olympus_Mons"})
    assert r.status_code == 422
    assert "not a recognised time zone" in r.text


def test_login_fills_in_a_missing_zone_and_never_overwrites_one(api):
    assert api.post("/users/signup", json=SIGNUP).json()["user"]["timezone"] is None

    first = api.post("/users/login", json={**CREDS, "timezone": "America/Los_Angeles"})
    assert first.json()["user"]["timezone"] == "America/Los_Angeles"

    elsewhere = api.post("/users/login", json={**CREDS, "timezone": "Asia/Tokyo"})
    assert elsewhere.json()["user"]["timezone"] == "America/Los_Angeles", (
        "logging in from another zone must not move where the user's day begins"
    )


def test_a_bad_zone_never_blocks_a_login(api):
    api.post("/users/signup", json=SIGNUP)
    r = api.post("/users/login", json={**CREDS, "timezone": "Mars/Olympus_Mons"})
    assert r.status_code == 200
    assert r.json()["user"]["timezone"] is None


def test_settings_changes_the_zone_and_refuses_unknown_names(api):
    token = api.post("/users/signup", json={**SIGNUP, "timezone": "America/Los_Angeles"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    ok = api.post("/users/me/timezone", json={"timezone": "Europe/London"}, headers=auth)
    assert ok.status_code == 200, ok.text
    assert ok.json()["timezone"] == "Europe/London"

    bad = api.post("/users/me/timezone", json={"timezone": "Europe/Atlantis"}, headers=auth)
    assert bad.status_code == 422
    assert api.get("/users/me", headers=auth).json()["timezone"] == "Europe/London"
