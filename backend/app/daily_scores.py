"""One score per local day: what the risk report and the trend chart both count.

A DAY, NOT A ROW
Nothing stops the evening test being taken twice against the same morning, and
the report used to count every row as a "scored day". A retake is not an
independent day of evidence -- the cues have been seen again, and the answers
may have been looked up -- so it inflated n, narrowed the intervals, and could
push a user past the 14-day minimum on repeats alone. Each local day now counts
once, by its FIRST attempt: that is the one taken under test conditions.

A DAY IN THE USER'S ZONE
Days are calendar dates in the user's own time zone (app/timezones.py), the
same day the check-in endpoints use, so an 18:00 evening check-in in Los
Angeles belongs to the day it was taken on rather than to tomorrow's UTC date.

THE WINDOW AND THE BASELINE
The period being judged is the last `window_days` local days, today included.
The baseline is the user's earliest scored days BEFORE that period, up to 14 --
the definition the report has always used. With none, the baseline is empty
and the trajectory is inconclusive. It is never the period itself: comparing a
period with itself gives 0% change by construction, which used to read as
"no concern".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from functools import lru_cache

from sqlalchemy.orm import Session

from app.models.checkin import EveningCheckin
from app.timezones import day_bounds_utc, local_date
from core.stats import MetricCI, bootstrap_stat_ci

BASELINE_DAYS = 14

# Trailing days behind each point of the trend's band. A single day is one
# observation and has no interval; a week is short enough to follow a change
# and long enough, when most days have a check-in, for a bootstrap interval.
ROLLING_DAYS = 7


@dataclass
class DayScore:
    score: float        # the first evening check-in of the day
    attempts: int       # >1 means retakes, which do not count


def load_day_scores(db: Session, user_id: int, zone: tzinfo) -> dict[date, DayScore]:
    """Every scored local day for a user, oldest first."""
    rows = (
        db.query(EveningCheckin.timestamp, EveningCheckin.daily_cognitive_score)
        .filter(EveningCheckin.user_id == user_id)
        .filter(EveningCheckin.daily_cognitive_score.isnot(None))
        .order_by(EveningCheckin.timestamp.asc(), EveningCheckin.id.asc())
        .all()
    )
    days: dict[date, DayScore] = {}
    for timestamp, score in rows:
        day = local_date(timestamp, zone)
        if day in days:
            days[day].attempts += 1
        else:
            days[day] = DayScore(score=float(score), attempts=1)
    return days


@dataclass
class Period:
    first_day: date
    last_day: date
    recent: list[float]      # one per scored day inside the period
    baseline: list[float]    # earliest scored days before it, up to BASELINE_DAYS
    scored_days: int         # all time, the minimum-data gate's count


def split_period(days: dict[date, DayScore], today: date, window_days: int) -> Period:
    first_day = today - timedelta(days=window_days - 1)
    ordered = sorted(days)
    return Period(
        first_day=first_day,
        last_day=today,
        recent=[days[d].score for d in ordered if first_day <= d <= today],
        baseline=[days[d].score for d in ordered if d < first_day][:BASELINE_DAYS],
        scored_days=len(days),
    )


@dataclass
class DayPoint:
    day: date
    score: float | None      # None: no check-in -- a gap, never a zero
    attempts: int
    rolling: MetricCI        # mean of the trailing ROLLING_DAYS, with its 95% CI


@lru_cache(maxsize=4096)
def _trailing_ci(scores: tuple[float, ...]) -> MetricCI:
    """core.stats' interval for one trailing window, memoised.

    Each call is a 2000-resample bootstrap, about 45 ms, so a 30-day chart cost
    well over a second -- every time the page opened. The result depends only
    on the ordered scores (the seed is fixed), so caching by them returns
    exactly what a fresh call would; only days whose window changed since
    (usually just the last week, after a new check-in) are recomputed. The
    shared object is only ever read.
    """
    # Fewer than core.stats.MIN_OBS_FOR_CI scores gives a point estimate with
    # no interval, and the chart draws no band there.
    return bootstrap_stat_ci(list(scores), name="rolling_mean")


def daily_points(days: dict[date, DayScore], first_day: date, last_day: date) -> list[DayPoint]:
    """Every calendar day in [first_day, last_day], scored or not."""
    points = []
    day = first_day
    while day <= last_day:
        trailing = tuple(
            days[d].score
            for d in (day - timedelta(days=k) for k in range(ROLLING_DAYS))
            if d in days
        )
        entry = days.get(day)
        points.append(DayPoint(
            day=day,
            score=entry.score if entry else None,
            attempts=entry.attempts if entry else 0,
            rolling=_trailing_ci(trailing),
        ))
        day += timedelta(days=1)
    return points


def period_bounds_utc(first_day: date, last_day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """[local midnight of first_day, local midnight after last_day), naive UTC."""
    return day_bounds_utc(first_day, zone)[0], day_bounds_utc(last_day, zone)[1]
