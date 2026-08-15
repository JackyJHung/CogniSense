"""FastAPI entry point for CogniSense backend."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.csrf import CsrfMiddleware, allowed_origins
from app.database import init_db
from app.notifications import scheduler
from app.routes import users, checkins, reports, reminders, push, recovery
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER


# uvicorn configures only its own loggers, so `logger.info(...)` from app code
# goes nowhere by default. That is fine for request handlers -- uvicorn already
# logs those -- but the push scheduler runs invisibly in the background, and
# without this there is no way to tell whether it is alive, sending, or quietly
# erroring. Override with COGNISENSE_LOG_LEVEL=DEBUG when diagnosing.
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CogniSense API",
    description=(
        "AI/ML-assisted tracker for early signs of cognitive decline. "
        "This is a self-tracking research tool, NOT a diagnostic device. "
        "Suggestions are not medical advice."
    ),
    version="0.1.0",
)

# CSRF must be added BEFORE CORS so that it runs AFTER it: Starlette applies
# middleware in reverse registration order, and a rejected preflight should
# never reach the CSRF check.
app.add_middleware(CsrfMiddleware)

# CORS. `allow_origins=["*"]` together with `allow_credentials=True` was not
# merely loose, it was inert: browsers refuse to send cookies to a wildcard
# origin, so cookie auth would have silently failed everywhere. Credentialed
# CORS requires an explicit origin list. Set COGNISENSE_ALLOWED_ORIGINS in
# deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    # Before anything else. In production this RAISES on an unsafe security
    # configuration rather than serving; in development it logs the same list,
    # so problems are visible long before a deploy. A warning that merely
    # scrolls past in a log is not a safeguard.
    config.validate()
    for key, value in config.summary().items():
        logger.info("config %-18s %s", key, value)

    init_db()
    # The reminder push loop. Without this running, notifications only ever
    # appear while somebody has the app open -- which defeats the point.
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    await scheduler.stop()


app.include_router(users.router)
app.include_router(checkins.router)
app.include_router(reports.router)
app.include_router(reminders.router)
app.include_router(push.router)
# Registered before users so that /recovery/* is never shadowed; it has its own
# prefix, but keeping credential routes together makes the ordering explicit.
app.include_router(recovery.router)


@app.get("/")
def root():
    return {
        "name": "CogniSense API",
        "version": "0.1.0",
        "status": "ok",
        "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Production: serve the built frontend from THIS origin.
#
# In development Vite proxies /api here, so the browser sees one origin and the
# SameSite=Strict session cookie works. Production needs the same property, and
# without this it would not have it -- the built app would be served from
# somewhere else and the cookie would never be sent.
#
# Registered last so every API route above wins the match, and GET-only so it
# cannot shadow a POST endpoint.
# ---------------------------------------------------------------------------
_DIST = Path(__file__).resolve().parents[2] / "web_app" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Serve a built file, else index.html so client-side routes resolve."""
        candidate = (_DIST / full_path).resolve()
        # `full_path` is attacker-controlled: without this containment check,
        # "../../backend/db/cognisense.db" would serve the database.
        if full_path and _DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
