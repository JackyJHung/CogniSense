"""Every environment-driven setting, in one place, validated at startup.

Configuration was spread across five modules, each reading os.environ with its
own default and its own idea of what counts as true. That is survivable until
the day it matters: the two settings that decide whether cookies are safe
(COOKIE_SECURE and ALLOWED_ORIGINS) were documented in a README section nobody
reads while deploying, with defaults tuned for localhost. A production deploy
that simply forgot them would come up looking healthy and be quietly insecure.

So this module does two things beyond collecting values:

  1. It names an ENVIRONMENT. Defaults differ between development and
     production rather than being one compromise that suits neither.

  2. `validate()` refuses to start a production server whose security settings
     are wrong. Failing closed on boot is the only failure mode an operator
     cannot miss -- a warning in a log scrolls past, and the app keeps serving.

Read once at import. Changing an environment variable needs a restart, which is
the honest behaviour: half the settings here are consumed at import time by the
modules that use them anyway.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        logger.warning("%s is not an integer; using %s", name, default)
        return default


def _csv(name: str, default: str) -> set[str]:
    raw = os.environ.get(name, default)
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

ENVIRONMENT = os.environ.get("COGNISENSE_ENV", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# --------------------------------------------------------------------------
# Cookies, origins, CSRF
# --------------------------------------------------------------------------

# Secure cookies are dropped over plain http, so this cannot default on in
# development -- but it MUST be on in production, which validate() enforces.
COOKIE_SECURE = _flag("COGNISENSE_COOKIE_SECURE", default=IS_PRODUCTION)

_DEV_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8000,http://127.0.0.1:8000"
)
ALLOWED_ORIGINS = _csv("COGNISENSE_ALLOWED_ORIGINS", "" if IS_PRODUCTION else _DEV_ORIGINS)

# --------------------------------------------------------------------------
# Proxy trust
# --------------------------------------------------------------------------

# Comma-separated addresses of reverse proxies whose X-Forwarded-For may be
# believed. EMPTY BY DEFAULT, and that default is the secure one: previously the
# header was trusted whenever it was present, so any caller could send
# "X-Forwarded-For: <random>" and get a fresh per-IP rate-limit budget on every
# request, defeating the throttle entirely.
#
# Set this to the address the proxy connects FROM (e.g. "127.0.0.1" for nginx on
# the same host). The proxy must also strip any inbound X-Forwarded-For, or a
# client can still prepend a forged entry.
TRUSTED_PROXIES = _csv("COGNISENSE_TRUSTED_PROXIES", "")

# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

SESSION_TTL_DAYS = _int("COGNISENSE_SESSION_TTL_DAYS", 30)

# Absolute lifetime is not enough on a shared or lost device: a session created
# 29 days ago and untouched for 28 of them is still valid. Idle expiry closes
# the window on abandoned sessions without forcing a daily login on someone who
# actually uses the app.
SESSION_IDLE_DAYS = _int("COGNISENSE_SESSION_IDLE_DAYS", 7)

# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------

VAPID_SUBJECT = os.environ.get("COGNISENSE_VAPID_SUBJECT", "mailto:admin@cognisense.local")
PUSH_TICK_SECONDS = _int("COGNISENSE_PUSH_TICK_SECONDS", 60)
PUSH_COOLDOWN_HOURS = _int("COGNISENSE_PUSH_COOLDOWN_HOURS", 6)
DISABLE_SCHEDULER = _flag("COGNISENSE_DISABLE_SCHEDULER")

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

# Absolute base URL the app is reached at, used to build links inside emails.
# A reset link is useless if it points at localhost, so production requires it.
PUBLIC_URL = os.environ.get("COGNISENSE_PUBLIC_URL", "http://localhost:5173").rstrip("/")

SMTP_HOST = os.environ.get("COGNISENSE_SMTP_HOST", "").strip()
SMTP_PORT = _int("COGNISENSE_SMTP_PORT", 587)
SMTP_USER = os.environ.get("COGNISENSE_SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("COGNISENSE_SMTP_PASSWORD", "")
SMTP_STARTTLS = _flag("COGNISENSE_SMTP_STARTTLS", default=True)
SMTP_FROM = os.environ.get("COGNISENSE_SMTP_FROM", "CogniSense <no-reply@cognisense.local>")

# With no SMTP host configured, emails are written to the log instead of sent.
# That keeps the whole flow runnable and testable offline, and is obvious in the
# output rather than silently doing nothing.
EMAIL_ENABLED = bool(SMTP_HOST)

# How long a link in an email stays usable.
RESET_TOKEN_MINUTES = _int("COGNISENSE_RESET_TOKEN_MINUTES", 60)
VERIFY_TOKEN_HOURS = _int("COGNISENSE_VERIFY_TOKEN_HOURS", 24)

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("COGNISENSE_LOG_LEVEL", "INFO").upper()


class ConfigError(RuntimeError):
    """Raised for a production configuration that is unsafe to serve."""


def problems() -> list[str]:
    """Security settings that are wrong for the declared environment."""
    found: list[str] = []

    if not IS_PRODUCTION:
        return found

    if not COOKIE_SECURE:
        found.append(
            "COGNISENSE_COOKIE_SECURE is off. Session cookies would be sent over "
            "plain http and could be read in transit."
        )

    if not ALLOWED_ORIGINS:
        found.append(
            "COGNISENSE_ALLOWED_ORIGINS is empty. Set it to the exact origin the "
            "app is served from, e.g. https://cognisense.example."
        )

    insecure = sorted(o for o in ALLOWED_ORIGINS if o.startswith("http://"))
    if insecure:
        found.append(
            "COGNISENSE_ALLOWED_ORIGINS contains plain-http origins in "
            f"production: {', '.join(insecure)}"
        )

    localhosts = sorted(
        o for o in ALLOWED_ORIGINS if "localhost" in o or "127.0.0.1" in o
    )
    if localhosts:
        found.append(
            "COGNISENSE_ALLOWED_ORIGINS still contains development origins: "
            f"{', '.join(localhosts)}"
        )

    if VAPID_SUBJECT.endswith("@cognisense.local"):
        found.append(
            "COGNISENSE_VAPID_SUBJECT is still the placeholder. Push services "
            "want a real contact address for the application server."
        )

    if "localhost" in PUBLIC_URL or PUBLIC_URL.startswith("http://"):
        found.append(
            f"COGNISENSE_PUBLIC_URL is {PUBLIC_URL!r}. Links inside password-reset "
            "emails are built from it, so a localhost or plain-http value sends "
            "users a link that does not work."
        )

    if EMAIL_ENABLED and SMTP_FROM.endswith("@cognisense.local>"):
        found.append(
            "COGNISENSE_SMTP_FROM is still the placeholder domain. Mail from an "
            "undeliverable sender is rejected or spam-filed by most providers."
        )

    return found


def validate(strict: bool | None = None) -> None:
    """Refuse to serve an unsafe production configuration.

    Called from the startup hook. `strict` defaults to IS_PRODUCTION: in
    development the same problems are only logged, so a developer is told what
    would break a deploy without being blocked from working.
    """
    strict = IS_PRODUCTION if strict is None else strict
    found = problems()
    if not found:
        logger.info("configuration OK (environment=%s)", ENVIRONMENT)
        return

    message = "Unsafe configuration for COGNISENSE_ENV=production:\n" + "\n".join(
        f"  - {p}" for p in found
    )
    if strict:
        # Failing to boot is the only signal an operator cannot scroll past.
        raise ConfigError(message)
    logger.warning(message)


def summary() -> dict:
    """Non-secret view of the active configuration, for the startup log."""
    return {
        "environment": ENVIRONMENT,
        "cookie_secure": COOKIE_SECURE,
        "allowed_origins": sorted(ALLOWED_ORIGINS),
        "trusted_proxies": sorted(TRUSTED_PROXIES) or "none (X-Forwarded-For ignored)",
        "session_ttl_days": SESSION_TTL_DAYS,
        "session_idle_days": SESSION_IDLE_DAYS,
        "scheduler": "disabled" if DISABLE_SCHEDULER else "enabled",
        "public_url": PUBLIC_URL,
        "email": f"smtp {SMTP_HOST}:{SMTP_PORT}" if EMAIL_ENABLED
                 else "NOT SENDING (no SMTP host; emails go to the log)",
    }
