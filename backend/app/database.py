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
    from app.models import user, checkin, image_association, reminder  # noqa: F401
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

    # users.morning_revisit_count
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "morning_revisit_count" not in user_cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN morning_revisit_count INTEGER DEFAULT 0 NOT NULL")
            )
