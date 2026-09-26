"""SQLite + SQLAlchemy setup for CogniSense."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base

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


def init_db(bind: Optional[Engine] = None):
    """Create all tables, then run the column migrations. Import models first so
    they register with Base. `bind` is the app's engine unless a test passes one."""
    bind = bind or engine
    from app.models import (  # noqa: F401
        user, checkin, image_association, reminder, push, session, security,
    )
    with _schema_lock(bind):
        Base.metadata.create_all(bind=bind)
        _run_lightweight_migrations(bind)


@contextmanager
def _schema_lock(bind: Engine):
    """Let one process at a time create or migrate the schema.

    Production runs two gunicorn workers, and each calls init_db() as it starts.
    On a fresh database both could find a table missing and both issue CREATE
    TABLE; the second failed with "table users already exists", so its worker
    never started, and gunicorn answers a worker that fails to boot by stopping
    the whole server. On an older database the same race would run an ALTER
    TABLE twice. An exclusive lock on a file beside the database makes the
    second process wait, then find the work already done.
    """
    database = bind.url.database
    if not database or database == ":memory:":
        yield   # an in-memory database belongs to a single process
        return
    with open(f"{database}.schema-lock", "a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            # Retries each second for ten seconds, then raises; the schema work
            # itself takes well under one.
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _run_lightweight_migrations(bind: Engine):
    """Idempotent column-add migrations for SQLite.

    `Base.metadata.create_all` only creates missing tables; it does NOT add columns
    that were introduced to existing models after a table was first built. For a
    demo-quality SQLite DB we hand-roll the ALTERs here instead of pulling in Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(bind)

    user_cols = {c["name"] for c in inspector.get_columns("users")}

    # users.morning_revisit_count
    if "morning_revisit_count" not in user_cols:
        with bind.begin() as conn:
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
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64)"))

    # users.last_push_at -- nullable, so no DEFAULT is needed.
    if "last_push_at" not in user_cols:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_push_at DATETIME"))

    # users.email / email_verified_at -- added with email-based recovery.
    if "email" not in user_cols:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(320)"))
    if "email_verified_at" not in user_cols:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME"))

    # One account per address, so "reset the account for this email" is never
    # ambiguous. A partial index lets any number of rows keep email NULL --
    # a plain UNIQUE would collide on the second null in some backends.
    with bind.begin() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
            "ON users(email) WHERE email IS NOT NULL"
        ))
