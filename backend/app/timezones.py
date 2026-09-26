"""Per-user time zones: which names are real, and where a user's day begins.

WHY AN IANA NAME AND NOT AN OFFSET
The check-in "day" used to be a UTC day, so for somebody in Los Angeles it
rolled over at 17:00 local time: an evening check-in landed on the next day's
record, and the one-morning-per-day guard looked at the wrong day. The browser
did report a UTC offset when subscribing to notifications, but an offset is a
snapshot -- it is wrong for half the year wherever clocks change, which is
most of the places CogniSense users live. A zone name (America/Los_Angeles)
carries the DST rules with it, so both the day boundary and push quiet hours
stay right across every transition.

UNKNOWN IS NOT THE SAME AS UTC
`users.timezone` is NULL until some client reports it. It is COMPUTED as UTC
-- exactly the old behaviour, so accounts from before this change see no
difference -- but it is stored as "unknown" rather than "UTC", so a client can
tell an account nobody has set from one whose owner chose UTC, and fill in only
the former. See app/routes/users.py for who may set it and when.

Windows has no system time zone database, so zoneinfo reads the `tzdata`
package there (it is in requirements.txt); on Linux it uses /usr/share/zoneinfo
and falls back to the same package.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 64

# Entries that load as zones but are not places. "localtime" links to whatever
# zone the server itself runs in -- UTC in the container -- so a user who
# "chose" it would get the server's day, not theirs. available_timezones() drops
# "posixrules", but on Debian and Ubuntu it lists "localtime", which their
# system database carries as a link to /etc/localtime. Windows reads the tzdata
# package, which has neither, so this only showed on Linux: CI's first run.
NOT_ZONES = frozenset({"localtime", "posixrules"})


@lru_cache(maxsize=1)
def _known_zones() -> frozenset[str]:
    # available_timezones() walks the whole database, so it runs once. A bare
    # ZoneInfo(name) probe would accept the NOT_ZONES entries too.
    return frozenset(available_timezones()) - NOT_ZONES


def is_valid(name: Optional[str]) -> bool:
    return (
        isinstance(name, str)
        and 0 < len(name) <= MAX_NAME_LENGTH
        and name in _known_zones()
    )


def validate(name: str) -> str:
    """Return `name` if it is a real IANA zone, else raise ValueError.

    Used by the request schemas, so an unknown name is a 422 that says what
    was wrong rather than a zone silently replaced by UTC.
    """
    if not is_valid(name):
        raise ValueError(
            f"{name!r} is not a recognised time zone. Use an IANA name such as "
            f"'America/Los_Angeles' or 'Europe/London'."
        )
    return name


def adopt_if_unknown(user, reported: Optional[str]) -> bool:
    """Take a device-reported zone for an account that has none. Never overwrites.

    Login and push-subscribe call this. Signup sets the zone outright and the
    settings page changes it on purpose; after signup, nothing a device merely
    reports moves it. Otherwise a trip, or a laptop borrowed from someone in
    another zone, would silently shift where the user's day begins -- and
    quietly undo whatever they chose in settings. A reported name that is not
    a real zone is ignored rather than refused: it must never block a login.
    """
    if getattr(user, "timezone", None) is None and is_valid(reported):
        user.timezone = reported
        return True
    return False


def zone_for(user) -> tzinfo:
    """The zone a user's days and quiet hours are counted in.

    Unknown -> UTC, as before this existed. A stored name that no longer
    loads (the database dropped it, the tzdata package went missing) also
    falls back to UTC, logged: a check-in must not fail over a time zone.
    """
    name = getattr(user, "timezone", None)
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("user %s has unusable time zone %r; using UTC",
                       getattr(user, "id", "?"), name)
        return timezone.utc


def local_date(instant: datetime, zone: tzinfo) -> date:
    """The calendar date `instant` falls on in `zone`. Naive means UTC."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone).date()


def day_bounds_utc(day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """[local midnight, next local midnight) for `day`, as naive UTC.

    Naive UTC because that is what SQLite stores in the timestamp columns and
    hands back, so the comparison in the query is like for like. The window is
    23 or 25 hours long on the days the clocks change, which is the point:
    a fixed 24h window from a fixed offset is exactly what drifted by an hour
    at every DST transition.
    """
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )
