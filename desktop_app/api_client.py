"""HTTP client for the desktop app: the one place that knows how to talk to the API.

WHY IT EXISTS
The Tkinter app predated session auth. It posted to /users/login, kept the
whole response as "the user", and never sent a credential again -- so every
call after login came back 401, and the dashboard itself failed, because login
now answers {"user": {...}, "token": ...} rather than a bare profile.

Holding the token here rather than in the UI means no screen can forget it:
every request goes through `_request`, which attaches `Authorization: Bearer`.

BEARER, NEVER THE COOKIE
Login also sets an HttpOnly session cookie, for browsers. A requests.Session
would quietly store it and send it back, and the desktop app would then be
authenticating by cookie without anyone having decided it should: a missing
token would go unnoticed, and logout would have two credentials to clear
instead of one. So this session refuses every cookie, and the token is the only
thing that says who is calling. It is held in memory only -- closing the app
discards it.

A 401 IS NOT AN ORDINARY ERROR
Once logged in, a 401 means the session is gone: expired, idle for too long,
or revoked by a password change or "log out everywhere" on another device.
`SessionExpired` lets the UI go back to the login screen and say so, instead of
showing a generic error over a dashboard where every button will fail the same
way.
"""
from __future__ import annotations

import os
import sys
from http.cookiejar import DefaultCookiePolicy
from typing import Any

import requests

DEFAULT_BACKEND_URL = os.getenv("COGNISENSE_BACKEND", "http://127.0.0.1:8000")

# (connect, read). The read side is generous because the first evening check-in
# after a server start loads both PyTorch models before it can answer.
TIMEOUT = (5, 60)

USER_AGENT = "CogniSense desktop (Tkinter)"

# The only calls made without a session. A 401 from these is a wrong password,
# not an expired session.
_UNAUTHENTICATED_PATHS = {"/users/login", "/users/signup"}


class ApiError(RuntimeError):
    """The server refused a request. `str()` is a sentence fit to show a user."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(describe(detail))


class SessionExpired(ApiError):
    """401 on an authenticated call: the session no longer exists server-side."""


class AlreadySubmitted(ApiError):
    """409 on the morning check-in or the evening test. Carries the existing
    check-in, which the server echoes so the client can show it without another
    request."""

    def __init__(self, status: int, detail: dict):
        super().__init__(status, detail)
        self.existing: dict = detail["existing"]


class ServerUnreachable(RuntimeError):
    """No HTTP answer at all: the backend is not running, or not at this URL."""


def describe(detail: Any) -> str:
    """Turn a FastAPI `detail` payload into one readable sentence.

    It arrives in three shapes: a plain string, a dict with a `message`
    (the 409s), or pydantic's list of validation errors. Showing the list raw
    would put `[{'type': 'string_too_short', 'loc': ['body', ...` in a dialog.
    """
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    if isinstance(detail, list):
        parts = []
        for err in detail:
            if not isinstance(err, dict):
                continue
            # loc is ["body", "<field>", ...]; the "body" prefix means nothing
            # to the person reading it, nor does pydantic's "Value error, "
            # in front of messages our own validators raise.
            field = ".".join(str(p) for p in err.get("loc", ())[1:]) or "request"
            msg = str(err.get("msg", "is invalid")).removeprefix("Value error, ")
            parts.append(f"{field}: {msg}")
        if parts:
            return "; ".join(parts)
    return str(detail)


def local_timezone() -> str | None:
    """This machine's IANA time zone, or None if it cannot be told reliably.

    Sent at signup and login so the account's day turns over at local midnight
    rather than at UTC midnight -- 17:00 in Los Angeles. None leaves the zone
    unset (counted as UTC) until a browser login or the web app's Settings
    fills it in. Only names the local zone database knows are offered: the
    server refuses unknown ones at signup.
    """
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    if sys.platform == "win32":
        candidates.append(_icu_default_zone())
    else:
        # /etc/localtime is normally a symlink into .../zoneinfo/<Area>/<City>.
        target = os.path.realpath("/etc/localtime")
        if "/zoneinfo/" in target:
            candidates.append(target.split("/zoneinfo/", 1)[1])
    try:
        from zoneinfo import available_timezones
        # Linux lists "localtime" (a link to the machine's own zone) among the
        # zones; the server refuses it, as it refuses "posixrules" -- see
        # backend/app/timezones.py -- so it must never be offered.
        known = available_timezones() - {"localtime", "posixrules"}
    except Exception:
        return None
    return next((c for c in candidates if c and c in known), None)


def _icu_default_zone() -> str | None:
    """Windows reports its zone by a Windows name ("Pacific Standard Time"),
    not an IANA one. The ICU library that ships with Windows 10 and later --
    the same one browsers use to answer this -- translates it."""
    try:
        import ctypes
        icu = ctypes.WinDLL("icu")
        fn = icu.ucal_getDefaultTimeZone
        fn.restype = ctypes.c_int32
        fn.argtypes = [ctypes.c_wchar_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int)]
        buf = ctypes.create_unicode_buffer(128)
        status = ctypes.c_int(0)
        length = fn(buf, 128, ctypes.byref(status))
        return buf.value[:length] if status.value <= 0 and length > 0 else None
    except (OSError, AttributeError):
        return None


class _DesktopSession(requests.Session):
    """The app's own transport: no cookie jar, and never an unbounded wait."""

    def __init__(self):
        super().__init__()
        # An empty allow-list admits no domain, so every Set-Cookie is dropped.
        self.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))

    def request(self, method, url, **kwargs):
        # requests has no session-wide timeout; without one, a server that
        # accepts the connection and never answers freezes the whole window.
        kwargs.setdefault("timeout", TIMEOUT)
        return super().request(method, url, **kwargs)


class CogniSenseClient:
    """One logged-in (or not yet logged-in) conversation with the backend.

    `session` is anything with requests' `request(method, url, json=,
    headers=)` shape. The app uses its own cookieless requests.Session; the
    tests pass FastAPI's TestClient, so they exercise the real routes, auth
    and validation rather than a mock of them.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BACKEND_URL,
        session: Any = None,
        device_timezone: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._http = session if session is not None else _DesktopSession()
        # The zone this device reports at signup and login. The app passes
        # local_timezone(); None reports nothing.
        self.device_timezone = device_timezone
        self._token: str | None = None
        self.user: dict | None = None

    @property
    def logged_in(self) -> bool:
        return self._token is not None

    # ------------------------------------------------------------------ auth

    def signup(self, **fields: Any) -> dict:
        if self.device_timezone:
            fields.setdefault("timezone", self.device_timezone)
        return self._adopt(self._request("POST", "/users/signup", json=fields))

    def login(self, username: str, password: str) -> dict:
        # The server adopts the zone only for an account that has none yet.
        body = {"username": username, "password": password}
        if self.device_timezone:
            body["timezone"] = self.device_timezone
        return self._adopt(self._request("POST", "/users/login", json=body))

    def logout(self, all_devices: bool = False) -> None:
        """End the session on the server, then forget it here regardless.

        A failed call must not leave the app looking logged in, and a session
        that already expired has nothing left to revoke.
        """
        try:
            if self._token is not None:
                self._request("POST", "/users/logout", json={"all_devices": all_devices})
        except (SessionExpired, ServerUnreachable):
            pass
        finally:
            self.forget()

    def forget(self) -> None:
        self._token = None
        self.user = None

    def _adopt(self, auth: dict) -> dict:
        # {"user": {...}, "token": "...", "token_type": "bearer", "expires_at": "..."}
        self._token = auth["token"]
        self.user = auth["user"]
        return self.user

    def me(self) -> dict:
        return self._request("GET", "/users/me")

    # -------------------------------------------------------------- check-ins

    def morning_today(self) -> dict | None:
        """Today's morning check-in, or None if there is not one yet."""
        try:
            return self._request("GET", f"/checkins/morning/today/{self._uid()}")
        except ApiError as err:
            if err.status == 404:
                return None
            raise

    def submit_morning(self, planned_activities: str) -> dict:
        return self._submit_once("/checkins/morning", {
            "user_id": self._uid(),
            "planned_activities": planned_activities,
        })

    def _submit_once(self, path: str, body: dict) -> dict:
        # The morning check-in and the evening test are once per day; a second
        # POST is a 409 carrying the first, which the screens show instead.
        try:
            return self._request("POST", path, json=body)
        except ApiError as err:
            if (err.status == 409 and isinstance(err.detail, dict)
                    and "existing" in err.detail):
                raise AlreadySubmitted(err.status, err.detail) from None
            raise

    def submit_midday(
        self,
        what_user_has_done: str,
        planned_remainder: str | None,
        response_latency_ms: int,
        morning_checkin_id: int | None,
    ) -> dict:
        return self._request("POST", "/checkins/midday", json={
            "user_id": self._uid(),
            "morning_checkin_id": morning_checkin_id,
            "what_user_has_done": what_user_has_done,
            "planned_remainder": planned_remainder or None,
            "response_latency_ms": response_latency_ms,
        })

    def submit_evening(
        self,
        morning_checkin_id: int,
        recalled_activities: str,
        association_responses: list[dict],
    ) -> dict:
        """`association_responses`: [{association_id, user_answer, response_latency_ms}]."""
        return self._submit_once("/checkins/evening", {
            "user_id": self._uid(),
            "morning_checkin_id": morning_checkin_id,
            "recalled_activities": recalled_activities,
            "association_responses": association_responses,
        })

    # ---------------------------------------------------------------- reports

    def risk_report(self) -> dict:
        return self._request("GET", f"/reports/risk-comparison/{self._uid()}")

    def daily_suggestions(self) -> dict:
        return self._request("GET", f"/reports/daily-suggestions/{self._uid()}")

    # -------------------------------------------------------------- transport

    def _uid(self) -> int:
        if self.user is None:
            raise SessionExpired(401, "You are not logged in.")
        return self.user["id"]

    def _request(self, method: str, path: str, json: Any = None) -> Any:
        headers = {"User-Agent": USER_AGENT}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            resp = self._http.request(
                method, f"{self.base_url}{path}", json=json, headers=headers,
            )
        except requests.RequestException as exc:
            raise ServerUnreachable(
                f"Could not reach the CogniSense server at {self.base_url}. "
                f"Is it running? ({exc.__class__.__name__})"
            ) from exc

        if resp.status_code == 401 and path not in _UNAUTHENTICATED_PATHS:
            self.forget()
            raise SessionExpired(401, _detail(resp))
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, _detail(resp))
        return resp.json() if resp.content else None


def _detail(resp: Any) -> Any:
    try:
        body = resp.json()
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"
    if isinstance(body, dict) and "detail" in body:
        return body["detail"]
    return body
