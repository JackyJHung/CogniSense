"""The trend report, and the one-score-per-day counting it shares with the risk report.

GET /reports/trend used to return the raw evening rows: bare numbers with no
interval, no baseline, no gaps, and no inconclusive state -- everything the
rest of the app refuses to show. It now returns every local day in the window
(a day without a check-in has no score, never a zero), a 95% band on the
trailing mean from core.stats, and the risk report's own trajectory on the same
inputs.

Building it exposed two defects in the risk report, pinned here too:
  - with no scored days before the period, the report compared the period with
    itself: 0% change by construction, shown as no concern
  - a retake of the evening test counted as another scored day
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import create_session  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.ml.risk_comparison import MINIMUM_CHECKINS_FOR_WARNING  # noqa: E402
from app.models.checkin import EveningCheckin  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes import reports  # noqa: E402

LA = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 9, 20)                     # in Los Angeles


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
    u = User(id=1, username="trend", hashed_password="x", age=70, gender="female",
             race="white", wake_time=time(7), sleep_time=time(22),
             timezone="America/Los_Angeles")
    db.add(u)
    db.commit()
    token = create_session(db, u)

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    # 13:00 on 20 September in Los Angeles.
    monkeypatch.setattr(reports, "_now", lambda: datetime(2026, 9, 20, 20, tzinfo=timezone.utc))
    fastapi_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(fastapi_app)
    client.headers["Authorization"] = f"Bearer {token}"
    yield client, db
    fastapi_app.dependency_overrides.clear()
    db.close()


def evening(db, day: date, score: float, hour: int = 19):
    """An evening check-in at `hour`:00 Los Angeles time on `day`."""
    local = datetime.combine(day, time(hour), tzinfo=LA)
    db.add(EveningCheckin(
        user_id=1, morning_checkin_id=1,
        timestamp=local.astimezone(timezone.utc).replace(tzinfo=None),
        recalled_activities="", association_responses=[],
        association_accuracy=score, daily_cognitive_score=score,
    ))
    db.commit()


def days_back(n: int) -> date:
    return TODAY - timedelta(days=n)


def trend(client, days=14) -> dict:
    r = client.get(f"/reports/trend/1?days={days}")
    assert r.status_code == 200, r.text
    return r.json()


def report(client) -> dict:
    r = client.get("/reports/risk-comparison/1")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------
# The series
# --------------------------------------------------------------------------

def test_every_day_of_the_window_has_a_point_and_a_gap_is_not_a_zero(env):
    client, db = env
    for n in (0, 2, 5):
        evening(db, days_back(n), 0.7)

    t = trend(client, days=14)
    assert [p["date"] for p in t["points"]] == [
        (TODAY - timedelta(days=13 - i)).isoformat() for i in range(14)
    ]
    by_day = {p["date"]: p for p in t["points"]}
    assert by_day[TODAY.isoformat()]["score"] == 0.7
    assert by_day[days_back(1).isoformat()]["score"] is None, "a missed day is a gap"
    assert sum(p["score"] is not None for p in t["points"]) == 3
    assert t["n_scored_days"] == 3
    assert t["timezone"] == "America/Los_Angeles"


def test_the_thirty_day_view_covers_thirty_local_days(env):
    client, db = env
    evening(db, days_back(20), 0.6)
    evening(db, days_back(40), 0.9)        # outside both windows

    t = trend(client, days=30)
    assert len(t["points"]) == 30
    assert t["points"][0]["date"] == days_back(29).isoformat()
    assert t["n_scored_days"] == 1


def test_an_evening_counts_on_its_own_local_day(env):
    """18:00 in Los Angeles is 01:00 UTC the next day; it belongs to the 19th."""
    client, db = env
    evening(db, days_back(1), 0.66, hour=18)

    by_day = {p["date"]: p["score"] for p in trend(client)["points"]}
    assert by_day[days_back(1).isoformat()] == 0.66
    assert by_day[TODAY.isoformat()] is None


def test_a_retake_does_not_count_twice(env):
    """The first attempt is the one taken under test conditions."""
    client, db = env
    evening(db, TODAY, 0.60, hour=18)
    evening(db, TODAY, 0.95, hour=19)      # the retake

    point = trend(client)["points"][-1]
    assert point["score"] == 0.60
    assert point["attempts"] == 2
    assert report(client)["n_scored_days"] == 1


def test_the_band_needs_three_days_and_brackets_the_mean(env):
    client, db = env
    evening(db, days_back(2), 0.60)
    evening(db, days_back(1), 0.70)

    p = trend(client)["points"][-1]
    assert p["rolling_scored_days"] == 2
    assert p["rolling_ci_low"] is None and p["rolling_ci_high"] is None, (
        "two days are too few for an interval; the chart must draw no band"
    )

    evening(db, TODAY, 0.80)
    p = trend(client)["points"][-1]
    assert p["rolling_scored_days"] == 3
    assert p["rolling_ci_low"] <= p["rolling_mean"] <= p["rolling_ci_high"]
    assert p["rolling_mean"] == pytest.approx(0.70, abs=1e-3)


# --------------------------------------------------------------------------
# The judgement, and its agreement with the risk report
# --------------------------------------------------------------------------

def test_too_little_data_is_inconclusive(env):
    client, db = env
    for n in range(5):
        evening(db, days_back(n), 0.3)

    t = trend(client)
    assert t["inconclusive"] is True and t["elevated_concern"] is False
    assert str(MINIMUM_CHECKINS_FOR_WARNING) in t["inconclusive_reason"]
    assert "5 days" in t["inconclusive_reason"]


def test_a_new_account_gets_no_average_rather_than_zero(env):
    client, _ = env
    r = report(client)
    assert r["user_recent_avg_score"] is None, "it used to say 'your recent average: 0%'"
    assert r["n_scored_days"] == 0
    assert r["inconclusive"] is True


def test_with_no_earlier_baseline_the_report_says_so_instead_of_no_change(env):
    """The self-comparison bug.

    Fourteen steady days, all inside the 14-day period, nothing before it. The
    report used to stand the period in for the missing baseline, get 0% change
    with a tidy interval around it, and show no banner at all -- an all-clear
    built from comparing the data with itself.
    """
    client, db = env
    for n in range(14):
        evening(db, days_back(n), 0.75 + (n % 3) * 0.01)

    r = report(client)
    assert r["inconclusive"] is True
    assert r["trajectory_change_pct"] is None
    assert "baseline" in r["inconclusive_reason"]

    t = trend(client)
    assert t["inconclusive"] is True
    assert t["baseline_avg"] is None and t["baseline_days"] == 0


def test_the_floor_warning_still_needs_no_baseline(env):
    client, db = env
    for n in range(14):
        evening(db, days_back(n), 0.18 + (n % 3) * 0.01)

    r = report(client)
    assert r["elevated_concern"] is True, "consistently very low scores warn without a baseline"
    assert trend(client)["elevated_concern"] is True


def test_retakes_cannot_carry_an_account_past_the_minimum(env):
    client, db = env
    for n in range(7):
        evening(db, days_back(n), 0.5, hour=18)
        evening(db, days_back(n), 0.5, hour=19)     # fourteen rows, seven days

    r = report(client)
    assert r["inconclusive"] is True
    assert "7 days" in r["inconclusive_reason"]


def _history(db, baseline_score, recent_score):
    # Fourteen days of baseline before the 14-day period, then fourteen inside it.
    for n in range(14, 28):
        evening(db, days_back(n), baseline_score + (n % 3) * 0.01)
    for n in range(14):
        evening(db, days_back(n), recent_score + (n % 3) * 0.01)


def test_steady_scores_are_neither_a_warning_nor_inconclusive(env):
    client, db = env
    _history(db, 0.80, 0.80)

    t = trend(client)
    assert t["baseline_days"] == 14 and t["n_scored_days"] == 14
    assert t["elevated_concern"] is False and t["inconclusive"] is False
    assert t["change_ci_low_pct"] <= 0 <= t["change_ci_high_pct"]


def test_a_clear_decline_is_flagged_by_both_and_they_agree(env):
    client, db = env
    _history(db, 0.80, 0.45)

    t, r = trend(client, days=14), report(client)
    assert t["elevated_concern"] is True and r["elevated_concern"] is True
    assert t["change_ci_high_pct"] < 0, "the whole interval is below zero"
    # Same inputs, same analysis: the chart and the report cannot disagree.
    assert t["change_pct"] == r["trajectory_change_pct"]
    assert t["change_ci_low_pct"] == r["trajectory_change_ci_low_pct"]
    assert t["change_ci_high_pct"] == r["trajectory_change_ci_high_pct"]
    assert round(t["recent_avg"], 3) == r["user_recent_avg_score"]
    assert t["concern_reason"] == r["concern_reason"]


def test_the_trend_keeps_the_disclaimer_and_its_old_series(env):
    client, db = env
    evening(db, TODAY, 0.7)
    t = trend(client)
    assert "NOT a medical diagnostic device" in t["disclaimer"]
    assert len(t["series"]) == 1


def test_the_memoised_band_is_exactly_what_core_stats_computes():
    """Caching must not change a single number, only when it is computed."""
    from app.daily_scores import _trailing_ci
    from core.stats import bootstrap_stat_ci

    scores = (0.61, 0.72, 0.68, 0.75)
    cached = _trailing_ci(scores)
    fresh = bootstrap_stat_ci(list(scores), name="rolling_mean")

    assert _trailing_ci(scores) is cached
    assert (cached.value, cached.ci_low, cached.ci_high, cached.n) == (
        fresh.value, fresh.ci_low, fresh.ci_high, fresh.n,
    )
