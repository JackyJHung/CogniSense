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
    from app.models import user, checkin, image_association  # noqa: F401
    Base.metadata.create_all(bind=engine)
