"""Standalone reminder scheduler, for running as its own process.

WHY THIS EXISTS
`scheduler.start()` is called from the FastAPI startup hook, which runs once per
worker process. Under `gunicorn --workers 2` that means TWO reminder loops on
one database, both ticking every 60 seconds.

The cooldown lives in `users.last_push_at`, so most of the time the second loop
reads a fresh timestamp and skips -- but the read and the write are not atomic.
Two ticks landing together can both see a stale value and both send, and the
user gets the same prompt twice. On a memory-support app that is worse than
merely untidy: a duplicate "what did you mean to do?" is indistinguishable, to
the person receiving it, from having already forgotten answering the first one.

So in a container deployment the web workers set COGNISENSE_DISABLE_SCHEDULER=1
and exactly one of these runs alongside them:

    python -m app.scheduler_main

Single process, no races, and it can be restarted independently of the API.

Run it with the same environment and the same database volume as the web
container, or it will have nothing to read.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app import config
from app.database import init_db
from app.notifications import scheduler

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

logger = logging.getLogger("app.scheduler_main")


async def _run() -> None:
    # Same validation the API performs, so a misconfigured scheduler fails at
    # boot rather than pushing with, say, a placeholder VAPID subject.
    config.validate()
    init_db()

    if config.DISABLE_SCHEDULER:
        logger.error(
            "COGNISENSE_DISABLE_SCHEDULER is set, so this process would do "
            "nothing. That flag is for the WEB containers; unset it here."
        )
        raise SystemExit(1)

    scheduler.start()
    logger.info("standalone reminder scheduler running")

    stop = asyncio.Event()

    def _request_stop(*_args) -> None:
        logger.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows has no add_signal_handler for these; fall back so this
            # module stays runnable on a dev machine.
            signal.signal(sig, _request_stop)

    await stop.wait()
    await scheduler.stop()
    logger.info("scheduler stopped cleanly")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
