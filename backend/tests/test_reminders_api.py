"""End-to-end test of the reminder flow over HTTP, on an in-memory database.

Mounts ONLY the reminders router rather than the whole app, so this runs without
torch or librosa -- `app.main` pulls in the check-in router, which imports the
PyTorch models. The reminder path itself has no ML dependency and should not
acquire one.

Skips cleanly when fastapi is not installed, so the suite still runs under a
bare numpy/sklearn interpreter.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in this interpreter")
pytest.importorskip("httpx", reason="httpx is required by fastapi's TestClient")

from datetime import time  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.models.reminder import ReminderCheck, ReminderItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes import reminders  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # reminders.IMAGE_DIR is resolved at import time and points at the real
    # backend/app/db/reminders/. Without this the upload test writes a file into
    # the running app's data directory and leaves it there.
    monkeypatch.setattr(reminders, "IMAGE_DIR", tmp_path / "reminder_images")
    reminders.IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # one shared in-memory DB across connections
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    session = TestingSession()
    session.add(User(
        id=1, username="tester", hashed_password="x", age=71,
        gender="female", race="white",
        wake_time=time(7, 0), sleep_time=time(22, 30),
    ))
    session.commit()
    session.close()

    app = FastAPI()
    app.include_router(reminders.router)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        c.session_factory = TestingSession  # type: ignore[attr-defined]
        yield c


def _add(client, description, label=None):
    r = client.post("/reminders", json={
        "user_id": 1, "description": description, "label": label,
    })
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------

def test_create_and_list_reminders(client):
    _add(client, "call the dentist about the crown")
    _add(client, "put the bins out")

    r = client.get("/reminders/1")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(i["status"] == "pending" for i in items)


def test_reminder_needs_words(client):
    r = client.post("/reminders", json={"user_id": 1})
    assert r.status_code == 422, "an item with no description and no label must be rejected"


def test_check_prompt_does_not_leak_the_items(client):
    """The whole test depends on the prompt not containing the answers."""
    _add(client, "call the dentist about the crown")
    _add(client, "pick up my blood pressure pills")

    r = client.post("/reminders/1/check")
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["n_items_active"] == 2
    serialized = str(body).lower()
    for leak in ("dentist", "crown", "pills", "blood"):
        assert leak not in serialized, f"the prompt leaked {leak!r}"


def test_full_flow_recall_then_aid_then_done(client):
    a = _add(client, "call the dentist about the crown")
    b = _add(client, "put the bins out")

    check = client.post("/reminders/1/check").json()

    r = client.post(
        f"/reminders/check/{check['check_id']}/recall",
        json={"recall_text": "I had to put the bins out", "response_latency_ms": 4200},
    )
    assert r.status_code == 200, r.text
    result = r.json()

    assert result["passed"] is True
    assert result["n_recalled"] == 1
    assert result["n_active"] == 2
    assert {m["item_id"] for m in result["matches"] if m["matched"]} == {b["id"]}
    # The aid: both items come back, including the one they missed.
    assert {i["id"] for i in result["items"]} == {a["id"], b["id"]}
    assert result["memory_aid_disclaimer"]

    done = client.post("/reminders/1/done", json={"item_ids": [b["id"]]})
    assert done.status_code == 200
    assert done.json()[0]["status"] == "done"

    remaining = client.get("/reminders/1").json()
    assert [i["id"] for i in remaining] == [a["id"]]


def test_failed_recall_still_returns_the_whole_list(client):
    """The safety property, over HTTP."""
    a = _add(client, "call the dentist about the crown")
    b = _add(client, "put the bins out")
    check = client.post("/reminders/1/check").json()

    result = client.post(
        f"/reminders/check/{check['check_id']}/recall",
        json={"recall_text": "no idea, sorry"},
    ).json()

    assert result["passed"] is False
    assert result["n_recalled"] == 0
    assert {i["id"] for i in result["items"]} == {a["id"], b["id"]}, (
        "a failed attempt must still return every reminder"
    )
    assert "here's your list" in result["feedback"].lower()


def test_a_check_cannot_be_answered_twice(client):
    _add(client, "put the bins out")
    check = client.post("/reminders/1/check").json()

    first = client.post(
        f"/reminders/check/{check['check_id']}/recall", json={"recall_text": "bins"}
    )
    assert first.status_code == 200

    second = client.post(
        f"/reminders/check/{check['check_id']}/recall", json={"recall_text": "bins"}
    )
    assert second.status_code == 409


def test_check_with_nothing_outstanding_is_rejected(client):
    r = client.post("/reminders/1/check")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "nothing_to_check"


def test_prospective_score_reports_no_trend_early(client):
    _add(client, "put the bins out")
    check = client.post("/reminders/1/check").json()
    client.post(f"/reminders/check/{check['check_id']}/recall", json={"recall_text": "bins"})

    r = client.get("/reminders/1/prospective-score")
    assert r.status_code == 200
    body = r.json()

    assert body["n_checks"] == 1
    assert body["recall_rate"] == 1.0
    # One check cannot support an interval or a trend.
    assert body["recall_rate_ci_low"] is None
    assert body["trend_available"] is False
    assert "at least" in (body["trend_note"] or "")


def test_image_upload_rejects_bad_extensions(client):
    item = _add(client, "take the pills", label="pills")

    bad = client.post(
        f"/reminders/{item['id']}/image",
        files={"image": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert bad.status_code == 400

    good = client.post(
        f"/reminders/{item['id']}/image",
        files={"image": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
    )
    assert good.status_code == 200
    stored = good.json()["image_path"]
    # The client-supplied filename must not appear in the stored path.
    assert "photo" not in stored.lower()
    assert stored.endswith(".png")


def test_dismissed_items_leave_the_active_list(client):
    a = _add(client, "call the dentist")
    _add(client, "put the bins out")

    client.post("/reminders/1/dismiss", json={"item_ids": [a["id"]]})
    active = client.get("/reminders/1").json()
    assert [i["description"] for i in active] == ["put the bins out"]
