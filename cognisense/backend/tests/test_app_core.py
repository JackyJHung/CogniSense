"""Unit tests for app/main.py, app/database.py, and the ORM models."""

from datetime import time

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.main import app, on_startup
from app.models.checkin import EveningCheckin, MorningCheckin
from app.models.image_association import (
    DEFAULT_ASSOCIATIONS,
    ImageAssociation,
    seed_associations,
)
from app.models.user import User


# ---------- main ----------

def test_root_advertises_the_api_and_the_disclaimer(client):
    body = client.get("/").json()
    assert body["name"] == "CogniSense API"
    assert body["version"] == "0.1.0"
    assert body["status"] == "ok"
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cors_is_enabled_for_mobile_and_desktop_clients(client):
    r = client.get("/health", headers={"Origin": "http://localhost:19006"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_all_routers_are_mounted():
    paths = {route.path for route in app.routes}
    assert {"/users/signup", "/users/login", "/users/{user_id}"} <= paths
    assert {"/checkins/morning", "/checkins/midday", "/checkins/evening"} <= paths
    assert {
        "/reports/risk-comparison/{user_id}",
        "/reports/daily-suggestions/{user_id}",
        "/reports/trend/{user_id}",
    } <= paths


def test_startup_initialises_the_database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    monkeypatch.setattr(database, "engine", engine)

    on_startup()

    tables = set(inspect(engine).get_table_names())
    assert {"users", "morning_checkins", "midday_checkins", "evening_checkins",
            "image_associations"} <= tables
    engine.dispose()


# ---------- database ----------

def test_get_db_yields_a_session_and_closes_it(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

    gen = database.get_db()
    session = next(gen)
    assert session.is_active
    with pytest.raises(StopIteration):
        next(gen)
    assert not session.in_transaction()
    engine.dispose()


# ---------- ORM models ----------

def test_username_is_unique(db):
    def make(username):
        return User(username=username, hashed_password="x", age=70, gender="female",
                    race="white", wake_time=time(7, 0), sleep_time=time(22, 0))

    db.add(make("dupe"))
    db.commit()
    db.add(make("dupe"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_aggregate_defaults_and_timestamps(db):
    user = User(username="defaults", hashed_password="x", age=70, gender="male",
                race="white", wake_time=time(6, 0), sleep_time=time(21, 0))
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.cumulative_recall_score == 0.0
    assert user.cumulative_checkin_count == 0
    assert user.created_at is not None
    assert user.updated_at is None


def test_checkin_relationships_backref_to_the_user(db):
    user = User(username="rel", hashed_password="x", age=70, gender="male",
                race="white", wake_time=time(6, 0), sleep_time=time(21, 0))
    db.add(user)
    db.commit()

    morning = MorningCheckin(user_id=user.id, planned_activities="walk",
                             presented_associations=[{"id": 1}])
    db.add(morning)
    db.commit()
    db.add(EveningCheckin(user_id=user.id, morning_checkin_id=morning.id,
                          recalled_activities="walked", association_responses=[],
                          association_accuracy=1.0))
    db.commit()
    db.refresh(user)

    assert [m.id for m in user.morning_checkins] == [morning.id]
    assert len(user.evening_checkins) == 1
    assert morning.presented_associations == [{"id": 1}]   # JSON round-trip


def test_seed_associations_populates_the_pool(db):
    seed_associations(db)

    rows = db.query(ImageAssociation).all()
    assert len(rows) == len(DEFAULT_ASSOCIATIONS) == 30
    assert {r.object_name for r in rows} == {a[0] for a in DEFAULT_ASSOCIATIONS}
    apple = db.query(ImageAssociation).filter(ImageAssociation.object_name == "apple").one()
    assert (apple.cue_word, apple.image_path, apple.category) == ("fruit", "apple.png", "food")


def test_seed_associations_is_idempotent(db):
    seed_associations(db)
    seed_associations(db)
    assert db.query(ImageAssociation).count() == len(DEFAULT_ASSOCIATIONS)


def test_default_associations_have_unique_objects_and_image_paths():
    objects = [a[0] for a in DEFAULT_ASSOCIATIONS]
    paths = [a[2] for a in DEFAULT_ASSOCIATIONS]
    assert len(set(objects)) == len(objects)
    assert len(set(paths)) == len(paths)
    assert all(p.endswith(".png") for p in paths)
