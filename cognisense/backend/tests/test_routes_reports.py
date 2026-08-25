"""Unit tests for app/routes/reports.py."""

import pytest

from app.data.research_benchmarks import NON_DIAGNOSTIC_DISCLAIMER


# ---------- risk comparison ----------

def test_risk_comparison_falls_back_to_cumulative_score_without_history(client, user_id):
    r = client.get(f"/reports/risk-comparison/{user_id}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["user_recent_avg_score"] == 0.0     # no check-ins yet
    # 70-year-old black female: 5.0% * 2.0 * 1.2 = 12.0%
    assert body["peer_expected_prevalence_pct"] == pytest.approx(12.0, abs=0.05)
    assert body["scd_peer_prevalence_pct"] == pytest.approx(10.1, abs=0.05)
    assert body["elevated_concern"] is False
    assert body["concern_reason"] is None
    assert len(body["suggestions"]) >= 3
    assert body["citations"]
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER


def test_risk_comparison_averages_only_scores_inside_the_window(client, user_id, make_history):
    make_history(user_id, {1: 0.8, 3: 0.9, 40: 0.1})   # the 40-day-old score is outside
    r = client.get(f"/reports/risk-comparison/{user_id}", params={"window_days": 14})
    assert r.json()["user_recent_avg_score"] == pytest.approx(0.85, abs=1e-3)


def test_risk_comparison_flags_a_drop_against_the_earlier_baseline(client, user_id, make_history):
    scores = {d: 0.9 for d in range(20, 34)}          # baseline outside the window
    scores.update({d: 0.4 for d in range(1, 8)})      # recent, much worse
    make_history(user_id, scores)

    body = client.get(f"/reports/risk-comparison/{user_id}", params={"window_days": 14}).json()
    assert body["user_recent_avg_score"] == pytest.approx(0.4, abs=1e-3)
    assert body["elevated_concern"] is True
    assert "dropped" in body["concern_reason"]
    assert "primary care doctor" in body["suggestions"][0]


def test_risk_comparison_no_concern_for_a_stable_user(client, user_id, make_history):
    scores = {d: 0.8 for d in range(20, 34)}
    scores.update({d: 0.82 for d in range(1, 8)})
    make_history(user_id, scores)

    body = client.get(f"/reports/risk-comparison/{user_id}").json()
    assert body["elevated_concern"] is False
    assert body["concern_reason"] is None


@pytest.mark.parametrize("window_days", [6, 91, 0, -1])
def test_risk_comparison_rejects_out_of_range_windows(client, user_id, window_days):
    r = client.get(f"/reports/risk-comparison/{user_id}", params={"window_days": window_days})
    assert r.status_code == 422


def test_risk_comparison_404_for_unknown_user(client):
    r = client.get("/reports/risk-comparison/4242")
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"


# ---------- daily suggestions ----------

def test_daily_suggestions_returns_three_cited_suggestions(client, user_id):
    r = client.get(f"/reports/daily-suggestions/{user_id}")
    assert r.status_code == 200
    body = r.json()

    assert len(body["suggestions"]) == 3
    assert len(set(body["suggestions"])) == 3
    # No elevated concern => no "see a doctor" prompt in this endpoint
    assert all("primary care doctor" not in s for s in body["suggestions"])
    assert "Lancet" in body["lancet_risk_factor_source"]
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER


def test_daily_suggestions_404_for_unknown_user(client):
    assert client.get("/reports/daily-suggestions/4242").status_code == 404


# ---------- trend ----------

def test_trend_returns_series_in_chronological_order(client, user_id, make_history):
    make_history(user_id, {5: 0.5, 1: 0.9, 3: 0.7})
    body = client.get(f"/reports/trend/{user_id}").json()

    assert body["user_id"] == user_id
    assert body["window_days"] == 30
    scores = [point["daily_cognitive_score"] for point in body["series"]]
    assert scores == [0.5, 0.7, 0.9]
    for point in body["series"]:
        assert point["timestamp"]
        assert set(point) == {
            "timestamp",
            "daily_cognitive_score",
            "association_accuracy",
            "activity_recall_accuracy",
            "avg_response_latency_ms",
        }
    assert body["disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER


def test_trend_respects_the_days_window(client, user_id, make_history):
    make_history(user_id, {2: 0.8, 45: 0.4})
    assert len(client.get(f"/reports/trend/{user_id}", params={"days": 30}).json()["series"]) == 1
    assert len(client.get(f"/reports/trend/{user_id}", params={"days": 60}).json()["series"]) == 2


def test_trend_is_empty_for_a_user_without_checkins(client, user_id):
    assert client.get(f"/reports/trend/{user_id}").json()["series"] == []


@pytest.mark.parametrize("days", [6, 181])
def test_trend_rejects_out_of_range_windows(client, user_id, days):
    assert client.get(f"/reports/trend/{user_id}", params={"days": days}).status_code == 422


def test_trend_404_for_unknown_user(client):
    assert client.get("/reports/trend/4242").status_code == 404
