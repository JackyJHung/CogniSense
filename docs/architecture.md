# CogniSense Architecture

## Why a shared backend

CogniSense supports three clients (desktop Tkinter, Android, iOS). All business logic, ML models, the database, and the risk-comparison engine live in **one place**: the FastAPI backend. Each client is a thin UI layer that calls the backend over HTTP.

Benefits:
- Retraining models or updating benchmarks updates all platforms at once.
- The research-benchmark constants are defined once and cited once.
- Adding a web client later is trivial — it's just another HTTP caller.

## Request flow (evening check-in)

```
   [Desktop / iOS / Android]
           |
           |  POST /checkins/evening
           |  { user_id, morning_checkin_id, recalled_activities, association_responses[] }
           v
   +----------------------+
   |  FastAPI router      |
   |  routes/checkins.py  |
   +----------------------+
           |
           | 1. Validate morning check-in exists and belongs to user
           | 2. Grade image-association test (exact match, per-question latency)
           | 3. Compute activity_overlap() on planned vs. recalled text
           | 4. Build 8-feature vector:
           |      - activity_recall_accuracy
           |      - association_accuracy
           |      - latency_z (vs. user's rolling baseline)
           |      - lexical_diversity
           |      - word_count_norm
           |      - latency_variance
           |      - checkin_consistency
           |      - speech_biomarker_score (from CNN if audio, else default)
           v
   +----------------------+
   |  PyTorch MLP         |  --> behavioral_biomarker_score in [0,1]
   +----------------------+
           |
           |  Composite:
           |    daily_score = 0.45*behav + 0.35*assoc_acc + 0.20*speech
           v
   +----------------------+
   |  SQLite via          |
   |  SQLAlchemy ORM      |  --> persist EveningCheckin row
   +----------------------+
           |
           v
   [Client receives daily results + disclaimer]
```

## Request flow (risk comparison)

```
   GET /reports/risk-comparison/{user_id}
           |
           v
   +---------------------------+
   |  risk_comparison.py       |
   |  1. Load last 14 days of  |
   |     daily_cognitive_score |
   |  2. Load earliest 14 days |
   |     as baseline           |
   |  3. Compute pct_change    |
   |  4. Fire attention warn   |
   |     if pct_change <= -20% |
   |     OR absolute < 0.35    |
   +---------------------------+
           |
           v
   +---------------------------+
   |  research_benchmarks.py   |
   |  compute_benchmark(age,   |
   |    gender, race)          |
   |  --> peer prevalence %,   |
   |      SCD peer rate,       |
   |      citations list       |
   +---------------------------+
           |
           v
   +---------------------------+
   |  personalized_suggestions |
   |  Filter Lancet 2024       |
   |  factors by life stage;   |
   |  doctor-visit rec first   |
   |  if elevated_concern      |
   +---------------------------+
           |
           v
   [Client renders report + disclaimer]
```

## Safety layer

Every response body in every endpoint carries the `NON_DIAGNOSTIC_DISCLAIMER` string, defined once in `app/data/research_benchmarks.py`. The UI components on each platform render it consistently (`Disclaimer` component on mobile, `_disclaimer()` helper on desktop). This prevents any single screen from silently dropping the disclaimer.

## File map

- `backend/app/data/research_benchmarks.py` — prevalence numbers + Lancet factors + disclaimer
- `backend/app/ml/speech_model.py` — 1D-CNN speech biomarker
- `backend/app/ml/behavioral_model.py` — MLP behavioral biomarker
- `backend/app/ml/risk_comparison.py` — trajectory + warning logic
- `backend/app/ml/train_models.py` — synthetic data training
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/routes/` — FastAPI routers (users, checkins, reports)
- `backend/app/main.py` — FastAPI entry point
- `desktop_app/main.py` — Tkinter desktop client
- `mobile_app/src/` — React Native client (iOS + Android)

## Phase 2 hooks (already stubbed)

- `models/checkin.py` captures `association_responses` JSON and `avg_response_latency_ms` — ready for trend charting.
- `routes/reports.py#get_trend` returns time-series data — ready to pipe into a Recharts component or matplotlib.
- `data/research_benchmarks.py#LANCET_2024_RISK_FACTORS` has population-attributable fractions per factor — ready to rank personalized suggestions by expected benefit.
- Alarm-lock: add an endpoint `GET /alarm-lock/{user_id}` returning `{unlocked: bool}` that toggles based on whether today's morning check-in has been completed. Mobile clients can integrate with OS lockscreen APIs.
