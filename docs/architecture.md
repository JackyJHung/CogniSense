# CogniSense Architecture

## Why a shared backend

CogniSense has two clients: a React web app, which phones install to the Home Screen as a PWA, and a Tkinter desktop app. All business logic, ML models, the database, and the risk-comparison engine live in **one place**: the FastAPI backend. Each client is a thin UI layer that calls the backend over HTTP.

Benefits:
- Retraining models or updating benchmarks updates every client at once.
- The research-benchmark constants are defined once and cited once.
- A new client is just another HTTP caller.

In production the backend also serves the built web app, so the browser sees a single origin — which is what lets the session cookie be `SameSite=Strict`. The desktop app authenticates with a bearer token instead.

## Request flow (evening check-in)

```
   [Web app / Desktop app]
           |
           |  POST /checkins/evening
           |  { user_id, morning_checkin_id, recalled_activities, association_responses[] }
           v
   +----------------------+
   |  FastAPI router      |
   |  routes/checkins.py  |
   +----------------------+
           |
           | 1. Session -> user; body user_id must be theirs (require_own_id)
           | 2. Morning check-in must exist and be theirs (owned_or_404)
           | 3. Grade image-association test (exact match, per-question latency)
           | 4. Compute activity_overlap() on planned vs. recalled text
           | 5. Build 8-feature vector:
           |      - activity_recall_accuracy
           |      - association_accuracy
           |      - latency_z (vs. user's rolling baseline)
           |      - lexical_diversity
           |      - word_count_norm
           |      - latency_variance
           |      - checkin_consistency
           |      - speech_biomarker_score (from the CNN if a recording was
           |        uploaded, else a neutral 0.75 stand-in)
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
   |  SQLAlchemy ORM      |  --> persist EveningCheckin row (the stored speech
   +----------------------+      score is null unless it was measured)
           |
           v
   [Client receives daily results + disclaimer]
```

## Request flow (risk comparison and trend)

```
   GET /reports/risk-comparison/{user_id}      GET /reports/trend/{user_id}?days=14|30
                    \                                  /
                     v                                v
   +---------------------------------------------------------------+
   |  daily_scores.py                                              |
   |  one score per LOCAL day (the user's zone): the day's first   |
   |  evening check-in -- a retake is not another day of evidence  |
   |  period   = the last N local days                             |
   |  baseline = earliest scored days BEFORE the period, up to 14  |
   +---------------------------------------------------------------+
                                 |
                                 v
   +---------------------------------------------------------------+
   |  risk_comparison.analyze_trajectory  (intervals: core.stats)  |
   |  < 14 scored days, no recent days, or no baseline             |
   |        --> inconclusive: "not enough to say yet"              |
   |  drop >= 20% AND its whole 95% CI below zero --> attention    |
   |  whole 95% CI of the recent mean below 0.35  --> attention    |
   +---------------------------------------------------------------+
                  |                                 |
                  v                                 v
   +-----------------------------+   +-----------------------------------+
   |  research_benchmarks.py     |   |  trend points: every day in the   |
   |  peer prevalence by age,    |   |  window (null = no check-in), the |
   |  gender, race; citations    |   |  trailing 7-day mean + 95% CI     |
   +-----------------------------+   +-----------------------------------+
                  |
                  v
   +-----------------------------+
   |  personalized_suggestions   |
   |  Lancet 2024 factors by     |
   |  life stage; doctor visit   |
   |  first if attention fires   |
   +-----------------------------+
                  |
                  v
   [Client renders report / chart + disclaimer]
```

Both endpoints run the same analysis on the same inputs, so for the same window the chart and the report cannot disagree.

## Safety layer

Every response that carries a score, a report, a suggestion or a memory check carries the `NON_DIAGNOSTIC_DISCLAIMER` string, defined once in `app/data/research_benchmarks.py`. Each client also renders the disclaimer on every screen (`Disclaimer` component on the web, `_disclaimer()` helper on desktop). This prevents any single screen from silently dropping it.

## File map

- `backend/app/main.py` — FastAPI entry point; serves `web_app/dist` in production
- `backend/app/config.py` — every environment setting; refuses an unsafe production config
- `backend/app/auth.py`, `csrf.py` — sessions (cookie or bearer), CSRF, authorisation checks
- `backend/app/ratelimit.py` — login, signup and recovery throttling
- `backend/app/timezones.py` — per-user IANA zones and local day bounds
- `backend/app/daily_scores.py` — one score per local day, shared by the report and the trend
- `backend/app/data/research_benchmarks.py` — prevalence numbers + Lancet factors + disclaimer
- `backend/app/ml/speech_model.py` — 1D-CNN speech biomarker
- `backend/app/ml/behavioral_model.py` — MLP behavioral biomarker
- `backend/app/ml/risk_comparison.py` — trajectory + warning logic
- `backend/app/ml/train_models.py` — synthetic data training
- `backend/app/ml/validate.py` — nested-CV validation harness with negative controls
- `backend/app/memory/prospective.py` — recall matching for the memory aid
- `backend/app/notifications/` — VAPID keys, push sender, reminder scheduler
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/routes/` — FastAPI routers (users, recovery, checkins, reports, reminders, push)
- `desktop_app/main.py` — Tkinter desktop client; `api_client.py` holds its session
- `web_app/src/` — React web client; `public/manifest.webmanifest` and `public/sw.js` make it installable and let it receive push

## Hooks for future work

- `models/checkin.py` stores every evening answer (`association_responses`, with per-cue latency), ready for item-level analysis.
- `data/research_benchmarks.py#LANCET_2024_RISK_FACTORS` has population-attributable fractions per factor — ready to rank personalized suggestions by expected benefit.
- Alarm-lock: add an endpoint `GET /alarm-lock/{user_id}` returning `{unlocked: bool}` that toggles based on whether today's morning check-in has been completed. Enforcing it needs a native app: a web app, installed or not, cannot touch the OS lock screen.
