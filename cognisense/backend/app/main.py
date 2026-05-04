"""FastAPI entry point for CogniSense backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routes import users, checkins, reports
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER


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
def on_startup():
    init_db()


app.include_router(users.router)
app.include_router(checkins.router)
app.include_router(reports.router)


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
