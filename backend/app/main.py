"""FastAPI entry point for CogniSense backend."""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.notifications import scheduler
from app.routes import users, checkins, reports, reminders, push
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER


# uvicorn configures only its own loggers, so `logger.info(...)` from app code
# goes nowhere by default. That is fine for request handlers -- uvicorn already
# logs those -- but the push scheduler runs invisibly in the background, and
# without this there is no way to tell whether it is alive, sending, or quietly
# erroring. Override with COGNISENSE_LOG_LEVEL=DEBUG when diagnosing.
logging.basicConfig(
    level=os.environ.get("COGNISENSE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(
    title="CogniSense API",
    description=(
        "AI/ML-assisted tracker for early signs of cognitive decline. "
        "This is a self-tracking research tool, NOT a diagnostic device. "
        "Suggestions are not medical advice."
    ),
    version="0.1.0",
)

# CORS: permissive for dev; tighten domain allow-list in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
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
