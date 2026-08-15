"""Cookie session transport and the CSRF defence that has to come with it.

THE TRADE THIS RESOLVES
Keeping the session token in localStorage means any XSS on the origin can read
it and walk away with a 30-day credential. Moving it into an HttpOnly cookie
closes that -- script cannot read the cookie at all -- but cookies are attached
by the browser automatically, on requests the user never intended to make. That
is CSRF, and swapping one hole for the other is not an improvement.

So the cookie is only half the change. Three layers guard it:

  1. SameSite=Strict
     The browser refuses to attach the cookie to any cross-site request. This
     alone stops classic CSRF in every browser that honours it, which is all of
     the current ones.

  2. Double-submit CSRF token
     A second, deliberately READABLE cookie holds a random value; the client
     echoes it in an X-CSRF-Token header. An attacking origin can cause the
     cookie to be SENT but cannot READ it, so it cannot produce the header.
     A cross-origin HTML form cannot set custom headers at all. This is the
     backstop for anything that slips past SameSite.

  3. Origin check
     When the browser supplies Origin on a state-changing request, it must be
     one we serve. Cheap, and catches misconfiguration.

AND THE PART THAT MAKES IT WORK AT ALL
The dev frontend runs on localhost:5173 and the API on 127.0.0.1:8000. Those are
different origins, so a SameSite=Strict cookie would never be sent and login
would appear to succeed and then fail on every subsequent call. The fix is not
to weaken the cookie to SameSite=None -- that re-opens exactly the hole this
module exists to close -- but to stop being cross-origin: Vite proxies /api to
the backend, so the browser sees one origin. See web_app/vite.config.ts.

NATIVE CLIENTS ARE UNAFFECTED
The desktop and mobile clients send `Authorization: Bearer`. A header is never
attached automatically by a browser, so header-authenticated requests are immune
to CSRF by construction and are skipped by this middleware.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import config

SESSION_COOKIE = "cognisense_session"
CSRF_COOKIE = "cognisense_csrf"
CSRF_HEADER = "x-csrf-token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Endpoints reachable before a session exists. They set cookies rather than
# relying on them, so there is no CSRF token to present yet.
CSRF_EXEMPT_PATHS = {
    "/users/login",
    "/users/signup",
    "/recovery/reset",
    "/health",
}

COOKIE_MAX_AGE = config.SESSION_TTL_DAYS * 24 * 60 * 60


def cookies_secure() -> bool:
    """Defaults on in production, off in development (Secure dies over http).

    app.config.validate() refuses to start a production server with this off.
    """
    return config.COOKIE_SECURE


def allowed_origins() -> set[str]:
    return config.ALLOWED_ORIGINS


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def attach_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    """Set both cookies on a login/signup/recovery response."""
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,      # script cannot read it; this is the XSS defence
        secure=cookies_secure(),
        samesite="strict",  # never sent cross-site; this is the CSRF defence
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=COOKIE_MAX_AGE,
        httponly=False,     # the client MUST read this one to echo it back
        secure=cookies_secure(),
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


class CsrfMiddleware(BaseHTTPMiddleware):
    """Enforces the double-submit check on cookie-authenticated writes.

    Implemented as middleware rather than a per-route dependency so a new
    endpoint cannot quietly ship without it. The common way CSRF protection
    fails is not that it was wrong -- it is that somebody added a route and
    forgot.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Bearer-authenticated callers cannot be CSRF'd: a browser will never
        # attach an Authorization header to a forged cross-site request.
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            return await call_next(request)

        # No session cookie means nothing is being ridden on; let auth reject it.
        cookie_token = request.cookies.get(SESSION_COOKIE)
        if not cookie_token:
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in allowed_origins():
            return _refuse("Request origin is not allowed")

        sent = request.headers.get(CSRF_HEADER)
        expected = request.cookies.get(CSRF_COOKIE)
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            return _refuse(
                "Missing or invalid CSRF token. Reload the page and try again."
            )

        return await call_next(request)


def _refuse(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": message})
