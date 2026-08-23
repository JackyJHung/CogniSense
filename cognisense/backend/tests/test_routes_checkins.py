"""Unit tests for app/routes/checkins.py."""

import io

import numpy as np
import pytest

from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER
from app.models.checkin import EveningCheckin, MiddayCheckin, MorningCheckin
from app.models.image_association import ImageAssociation
from app.models.user import User
from app.routes import checkins as checkins_route


PLANNED = "walk the dog, buy groceries, call sister, read book"


@pytest.fixture(autouse=True)
def isolate_route_globals(monkeypatch, tmp_path):
    """The route caches ML scorers in module globals and writes uploads to
    backend/db/audio; keep both out of the way of other tests and the repo."""
    monkeypatch.setattr(checkins_route, "_speech_scorer", None)
    monkeypatch.setattr(checkins_route, "_behavioral_scorer", None)
    monkeypatch.setattr(checkins_route, "AUDIO_DIR", tmp_path / "audio")
    (tmp_path / "audio").mkdir()


@pytest.fixture
def morning(client, user_id):
    r = client.post("/checkins/morning", json={"user_id": user_id, "planned_activities": PLANNED})
    assert r.status_code == 201, r.text
    return r.json()


def _evening_responses(morning, n_correct=5):
    return [
        {
            "association_id": a["id"],
            "user_answer": a["object_name"] if i < n_correct else "definitely-wrong",
            "response_latency_ms": 1200 + i * 100,
        }
        for i, a in enumerate(morning["presented_associations"])
    ]


# ---------- morning ----------

def test_morning_seeds_pool_and_returns_five_distinct_associations(morning, db):
    presented = morning["presented_associations"]
    assert len(presented) == 5
    assert len({p["id"] for p in presented}) == 5
    for p in presented:
        assert {"id", "object_name", "cue_word", "image_path"} == set(p)
    assert morning["planned_activities"] == PLANNED
    assert morning["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER
    assert db.query(ImageAssociation).count() == 30
    assert db.query(MorningCheckin).count() == 1


def test_morning_reuses_the_seeded_pool_on_later_checkins(client, user_id, morning, db):
    client.post("/checkins/morning", json={"user_id": user_id, "planned_activities": "rest"})
    assert db.query(ImageAssociation).count() == 30
    assert db.query(MorningCheckin).count() == 2


def test_morning_404_for_unknown_user(client):
    r = client.post("/checkins/morning", json={"user_id": 4242, "planned_activities": PLANNED})
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"


def test_morning_500_when_pool_is_under_seeded(client, user_id, db, monkeypatch):
    monkeypatch.setattr(checkins_route, "seed_associations", lambda session: None)
    r = client.post("/checkins/morning", json={"user_id": user_id, "planned_activities": PLANNED})
    assert r.status_code == 500
    assert "under-seeded" in r.json()["detail"]


def test_morning_requires_planned_activities(client, user_id):
    assert client.post("/checkins/morning", json={"user_id": user_id}).status_code == 422


# ---------- morning audio upload ----------

def _wav_bytes(duration_s=1.0, sr=16000):
    import soundfile as sf

    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    buf = io.BytesIO()
    sf.write(buf, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr, format="WAV")
    return buf.getvalue()


def test_audio_upload_stores_file_and_speech_score(client, morning, db):
    r = client.post(
        f"/checkins/morning/{morning['id']}/audio",
        files={"audio": ("plans.wav", _wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 200, r.text
    score = r.json()["speech_biomarker_score"]
    assert 0.0 <= score <= 1.0
    assert r.json()["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER

    stored = db.query(MorningCheckin).filter(MorningCheckin.id == morning["id"]).one()
    assert stored.audio_file_path.endswith("plans.wav")
    assert stored.speech_biomarker_score == pytest.approx(score)


def test_audio_upload_records_none_when_scoring_fails(client, morning, db):
    r = client.post(
        f"/checkins/morning/{morning['id']}/audio",
        files={"audio": ("corrupt.wav", b"not really audio", "audio/wav")},
    )
    assert r.status_code == 200
    assert r.json()["speech_biomarker_score"] is None

    stored = db.query(MorningCheckin).filter(MorningCheckin.id == morning["id"]).one()
    assert stored.audio_file_path is not None
    assert stored.speech_biomarker_score is None


def test_audio_upload_404_for_unknown_checkin(client):
    r = client.post(
        "/checkins/morning/9999/audio",
        files={"audio": ("plans.wav", _wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Morning check-in not found"


# ---------- midday ----------

def test_midday_persists_and_echoes_payload(client, user_id, morning, db):
    r = client.post("/checkins/midday", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "what_user_has_done": "walked dog bought groceries",
        "planned_remainder": "call sister read book",
        "response_latency_ms": 1400,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["what_user_has_done"] == "walked dog bought groceries"
    assert body["planned_remainder"] == "call sister read book"
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER

    stored = db.query(MiddayCheckin).one()
    assert stored.morning_checkin_id == morning["id"]
    assert stored.response_latency_ms == 1400


def test_midday_optional_fields_default_to_none(client, user_id, db):
    r = client.post("/checkins/midday", json={"user_id": user_id, "what_user_has_done": "rested"})
    assert r.status_code == 201
    assert r.json()["planned_remainder"] is None

    stored = db.query(MiddayCheckin).one()
    assert stored.morning_checkin_id is None
    assert stored.response_latency_ms is None


def test_midday_404_for_unknown_user(client):
    r = client.post("/checkins/midday", json={"user_id": 4242, "what_user_has_done": "x"})
    assert r.status_code == 404


# ---------- evening ----------

def test_evening_grades_associations_and_scores_the_day(client, user_id, morning, db):
    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": "walked dog grocery store called sister read book",
        "association_responses": _evening_responses(morning, n_correct=4),
    })
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["association_accuracy"] == 0.8
    assert body["avg_response_latency_ms"] == 1400
    assert 0 <= body["activity_recall_accuracy"] <= 1
    assert 0 <= body["daily_cognitive_score"] <= 1
    assert 0 <= body["behavioral_biomarker_score"] <= 1
    assert body["speech_biomarker_score"] == 0.75   # default when no audio was scored
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER

    stored = db.query(EveningCheckin).one()
    assert len(stored.association_responses) == 5
    graded = {g["association_id"]: g for g in stored.association_responses}
    assert sum(g["correct"] for g in graded.values()) == 4
    for g in graded.values():
        assert {"cue_word", "expected_answer", "user_answer", "response_latency_ms"} <= set(g)


def test_evening_answer_grading_ignores_case_and_whitespace(client, user_id, morning):
    responses = [
        {
            "association_id": a["id"],
            "user_answer": f"  {a['object_name'].upper()} ",
            "response_latency_ms": 1000,
        }
        for a in morning["presented_associations"]
    ]
    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": responses,
    })
    assert r.json()["association_accuracy"] == 1.0


def test_perfect_recall_scores_higher_than_total_failure(client, user_id, db):
    def score(n_correct, recalled):
        m = client.post(
            "/checkins/morning", json={"user_id": user_id, "planned_activities": PLANNED}
        ).json()
        r = client.post("/checkins/evening", json={
            "user_id": user_id,
            "morning_checkin_id": m["id"],
            "recalled_activities": recalled,
            "association_responses": _evening_responses(m, n_correct=n_correct),
        })
        return r.json()["daily_cognitive_score"]

    assert score(5, PLANNED) > score(0, "not sure")


def test_evening_uses_morning_speech_score_when_available(client, morning, user_id, db):
    stored_morning = db.query(MorningCheckin).filter(MorningCheckin.id == morning["id"]).one()
    stored_morning.speech_biomarker_score = 0.31
    db.commit()

    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": _evening_responses(morning),
    })
    assert r.json()["speech_biomarker_score"] == 0.31


def test_evening_falls_back_to_heuristic_when_the_model_fails(client, user_id, morning, monkeypatch):
    def boom():
        raise RuntimeError("checkpoint unreadable")

    monkeypatch.setattr(checkins_route, "_get_behavioral_scorer", boom)

    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": _evening_responses(morning),
    })
    assert r.status_code == 201
    body = r.json()
    # heuristic = 0.5*assoc + 0.3*activity_recall + 0.2*speech, all at their max here
    expected = 0.5 * 1.0 + 0.3 * body["activity_recall_accuracy"] + 0.2 * 0.75
    assert body["behavioral_biomarker_score"] == pytest.approx(expected, abs=1e-3)


def test_evening_updates_user_rolling_aggregates(client, user_id, morning, db):
    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": _evening_responses(morning),
    })
    daily = r.json()["daily_cognitive_score"]

    user = db.query(User).filter(User.id == user_id).one()
    assert user.cumulative_checkin_count == 1
    assert user.cumulative_recall_score == pytest.approx(daily, abs=1e-3)


def test_rolling_recall_score_is_a_running_mean(client, user_id, db):
    dailies = []
    for n_correct in (5, 0):
        m = client.post(
            "/checkins/morning", json={"user_id": user_id, "planned_activities": PLANNED}
        ).json()
        r = client.post("/checkins/evening", json={
            "user_id": user_id,
            "morning_checkin_id": m["id"],
            "recalled_activities": PLANNED,
            "association_responses": _evening_responses(m, n_correct=n_correct),
        })
        dailies.append(r.json()["daily_cognitive_score"])

    user = db.query(User).filter(User.id == user_id).one()
    assert user.cumulative_checkin_count == 2
    assert user.cumulative_recall_score == pytest.approx(sum(dailies) / 2, abs=1e-3)


def test_evening_400_for_an_association_not_presented(client, user_id, morning):
    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": [
            {"association_id": 9999, "user_answer": "apple", "response_latency_ms": 1000}
        ],
    })
    assert r.status_code == 400
    assert "was not presented this morning" in r.json()["detail"]


def test_evening_403_when_morning_belongs_to_another_user(client, morning, signup_payload):
    other = client.post("/users/signup", json=signup_payload(username="intruder")).json()
    r = client.post("/checkins/evening", json={
        "user_id": other["id"],
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": _evening_responses(morning),
    })
    assert r.status_code == 403
    assert r.json()["detail"] == "Morning check-in does not belong to user"


def test_evening_404_for_unknown_user_and_unknown_morning(client, user_id, morning):
    r = client.post("/checkins/evening", json={
        "user_id": 4242,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": [],
    })
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"

    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": 9999,
        "recalled_activities": PLANNED,
        "association_responses": [],
    })
    assert r.status_code == 404
    assert r.json()["detail"] == "Morning check-in not found"


def test_evening_with_no_responses_scores_zero_accuracy(client, user_id, morning):
    r = client.post("/checkins/evening", json={
        "user_id": user_id,
        "morning_checkin_id": morning["id"],
        "recalled_activities": PLANNED,
        "association_responses": [],
    })
    assert r.status_code == 201
    assert r.json()["association_accuracy"] == 0.0
    assert r.json()["avg_response_latency_ms"] == 0


def test_lazy_scorer_getters_cache_their_instances():
    first = checkins_route._get_behavioral_scorer()
    assert checkins_route._get_behavioral_scorer() is first

    first_speech = checkins_route._get_speech_scorer()
    assert checkins_route._get_speech_scorer() is first_speech
