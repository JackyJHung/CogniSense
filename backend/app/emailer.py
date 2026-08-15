"""Sending mail, with an honest fallback when there is nowhere to send it.

Two backends, chosen by whether COGNISENSE_SMTP_HOST is set:

  SMTP     a real server, used when configured
  console  writes the whole message, link included, to the log

The console backend is not a stub that pretends to work. It exists because the
alternative -- an app that accepts an email address, says "check your inbox",
and silently drops the message -- is the worst possible behaviour for a recovery
path. Written to the log, the flow stays fully testable offline and the reset
link is right there to click; the startup banner says plainly that nothing is
being delivered.

Sending is best-effort and never raises into a request. A failed send must not
turn "we've emailed you a link" into a 500, both because the caller cannot act
on it and because a difference in response between "address exists" and
"address does not" is exactly the enumeration oracle these endpoints avoid.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app import config

logger = logging.getLogger(__name__)


def _send_smtp(message: EmailMessage) -> bool:
    try:
        if config.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT, timeout=15,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
        with server:
            server.ehlo()
            if config.SMTP_STARTTLS and config.SMTP_PORT != 465:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(message)
        logger.info("sent %r to %s", message["Subject"], message["To"])
        return True
    except Exception:
        # Broad on purpose: DNS, TLS, auth, greylisting, timeouts. None of them
        # should surface to the user as a failed request.
        logger.exception("failed to send %r to %s", message["Subject"], message["To"])
        return False


def _send_console(message: EmailMessage) -> bool:
    logger.warning(
        "EMAIL NOT SENT (no SMTP configured). It would have been:\n"
        "  To:      %s\n"
        "  Subject: %s\n"
        "%s",
        message["To"], message["Subject"], message.get_content().strip(),
    )
    return True


def send_email(to: str, subject: str, body: str) -> bool:
    message = EmailMessage()
    message["From"] = config.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    if config.EMAIL_ENABLED:
        return _send_smtp(message)
    return _send_console(message)


# --------------------------------------------------------------------------
# The two messages this app sends
# --------------------------------------------------------------------------

def send_verification(to: str, username: str, token: str) -> bool:
    link = f"{config.PUBLIC_URL}/verify-email?token={token}"
    return send_email(
        to,
        "Confirm your email for CogniSense",
        f"""Hello {username},

Please confirm this address so it can be used to get back into your CogniSense
account if you ever forget your password:

    {link}

The link works once and expires in {config.VERIFY_TOKEN_HOURS} hours.

If you did not add this address to a CogniSense account, you can ignore this
message -- nothing has changed and the address will not be used.
""",
    )


def send_password_reset(to: str, username: str, token: str) -> bool:
    link = f"{config.PUBLIC_URL}/reset-password?token={token}"
    return send_email(
        to,
        "Reset your CogniSense password",
        f"""Hello {username},

Someone asked to reset the password for your CogniSense account. If that was
you, follow this link to choose a new one:

    {link}

The link works once and expires in {config.RESET_TOKEN_MINUTES} minutes.

If it was not you, you can ignore this message. Your password has not changed,
and nobody can use this link without opening it from your inbox. If you keep
receiving these, change your password and consider generating new recovery
codes.
""",
    )
