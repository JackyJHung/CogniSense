"""SQLite + SQLAlchemy setup for CogniSense."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "db"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "cognisense.db"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yield a session, ensure close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Import models first so they register with Base."""
    from app.models import (  # noqa: F401
        user, checkin, image_association, reminder, push, session, security,
    )
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def _run_lightweight_migrations():
    """Idempotent column-add migrations for SQLite.

    `Base.metadata.create_all` only creates missing tables; it does NOT add columns
    that were introduced to existing models after a table was first built. For a
    demo-quality SQLite DB we hand-roll the ALTERs here instead of pulling in Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    user_cols = {c["name"] for c in inspector.get_columns("users")}

    # users.morning_revisit_count
    if "morning_revisit_count" not in user_cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN morning_revisit_count INTEGER DEFAULT 0 NOT NULL")
            )

    # users.timezone -- IANA name, replacing utc_offset_minutes. Existing rows
    # are left NULL ("not known yet", counted as UTC, which is what they got
    # before). Their old offset is not converted: -420 is Los Angeles in
    # summer, Denver in winter and Phoenix all year, so any guess would be
    # confidently wrong for some of them. Clients fill it in -- see
    # app/routes/users.py. The retired utc_offset_minutes column is not
    # created for new databases and is left alone in old ones.
    if "timezone" not in user_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64)"))

    # users.last_push_at -- nullable, so no DEFAULT is needed.
    if "last_push_at" not in user_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_push_at DATETIME"))

    # users.email / email_verified_at -- added with email-based recovery.
    if "email" not in user_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(320)"))
    if "email_verified_at" not in user_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME"))

    # One account per address, so "reset the account for this email" is never
    # ambiguous. A partial index lets any number of rows keep email NULL --
    # a plain UNIQUE would collide on the second null in some backends.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
            "ON users(email) WHERE email IS NOT NULL"
        ))
