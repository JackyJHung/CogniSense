"""FastAPI entry point for CogniSense backend."""

import logging
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    version="1.0.0",
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


# Set on requests that arrived under /api; see ApiPrefix.
VIA_API_PREFIX = "cognisense.via_api_prefix"


class ApiPrefix:
    """Answer /api/... as well as the root paths.

    The web client calls "/api/users/login" and so on (web_app/src/lib/api.ts).
    In development Vite's proxy strips the prefix before the request gets here.
    In production nothing did: every call from the built app fell through to
    the SPA fallback below, which answered GETs with index.html and POSTs with
    405, so the deployed web app could not even log in. This strips it the way
    the proxy does, and marks the request so that an /api path matching no
    route is a 404 rather than the page. Native clients keep calling the root.

    Added last, so it runs first: CSRF and CORS see the same path as in
    development, and the CSRF exemptions still match.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[len("/api"):] or "/"
                raw = scope.get("raw_path")
                if raw is not None:
                    scope["raw_path"] = raw[len(b"/api"):] or b"/"
                scope[VIA_API_PREFIX] = True
        await self.app(scope, receive, send)


app.add_middleware(ApiPrefix)


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
def root(request: Request):
    """The site root: the app for a browser, a JSON banner for anything else.

    In production the frontend is served from this same origin, and this route
    is registered before the SPA fallback below -- so without the check, anyone
    opening the bare domain, and the installed web app (start_url "/"), got
    this JSON instead of the app. A browser navigation asks for text/html; API
    clients and scripts do not. `Vary: Accept` stops a cache between here and
    the user from handing one kind of caller the other kind's answer.
    """
    headers = {"Vary": "Accept"}
    wants_page = "text/html" in request.headers.get("accept", "")
    if _DIST.is_dir() and wants_page and not request.scope.get(VIA_API_PREFIX):
        return FileResponse(_DIST / "index.html", headers=headers)
    return JSONResponse(
        {
            "name": "CogniSense API",
            "version": "1.0.0",
            "status": "ok",
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        headers=headers,
    )


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

# FileResponse types files by extension through `mimetypes`, whose table varies
# with the Python version and whatever the host OS registers. Pinned so the
# manifest that makes the app installable is served as what it is everywhere,
# including the slim production image.
mimetypes.add_type("application/manifest+json", ".webmanifest")

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str, request: Request):
        """Serve a built file, else index.html so client-side routes resolve."""
        if request.scope.get(VIA_API_PREFIX):
            # An API call to a path no route has. The page here would reach the
            # client as a 200 it then fails to parse.
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (_DIST / full_path).resolve()
        # `full_path` is attacker-controlled: without this containment check,
        # "../../backend/db/cognisense.db" would serve the database.
        if full_path and _DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
