# CogniSense

AI/ML application for early-risk screening of Alzheimer's disease and related dementias (ADRD) using speech patterns and behavioral biomarkers captured via microphone and camera. CogniSense delivers daily check-ins, image-association memory tasks, biweekly/monthly reports, and personalized prevention guidance grounded in peer-reviewed research.

> **Important:** CogniSense is a research and self-tracking tool. It is **NOT** a medical diagnostic device and does not replace professional evaluation. Any output from this app is a suggestion, not professional advice. If you or a loved one are experiencing worsening memory concerns, please consult a licensed physician or neurologist.

## Architecture

CogniSense uses a **shared Python/PyTorch backend** (FastAPI + SQLite) that serves both a **desktop client** (Tkinter) and **mobile clients** (Android / iOS via React Native, scaffolded). Cross-platform means the ML models, data store, and risk comparison logic only need to be maintained in one place.

```
cognisense/
├── backend/             # FastAPI server + PyTorch ML models + SQLite DB
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── database.py          # SQLite setup
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── models/              # ORM models
│   │   ├── routes/              # API endpoints (users, check-ins, reports)
│   │   ├── ml/                  # PyTorch speech + behavioral models
│   │   └── data/                # Research benchmarks (age/gender/race)
│   ├── tests/
│   └── requirements.txt
├── desktop_app/         # Tkinter desktop client
├── mobile_app/          # React Native cross-platform (iOS + Android) scaffold
└── docs/                # Data sources, model cards, architecture notes
```

## Core feature set (Phase 1 — this build)

1. **Onboarding** — age, gender, race/ethnicity, wake time, sleep time
2. **Morning check-in** — record today's plans + present 5 image associations
3. **Midday check-in** — light recall prompt
4. **Evening check-in** — recall today's activities + test image associations
5. **Speech biomarker capture** — record short voice sample, extract MFCC features, score with PyTorch 1D-CNN
6. **Behavioral biomarker scoring** — recall accuracy, response latency, linguistic features → PyTorch MLP
7. **Research-grounded risk comparison** — compares user scores against age/gender/race benchmarks from Alzheimer's Association 2024 Facts & Figures, CDC BRFSS, and the 2024 Lancet Commission
8. **Safety layer** — every report, warning, and suggestion carries the non-diagnostic disclaimer

## Phase 2 (next)

- Biweekly / monthly longitudinal reports with trend charts
- Attention warning triggered by sustained deviation from benchmarks
- Alarm-lock mode (phone unlocks only on check-in completion)
- Research-backed daily activity recommendations driven by the 14 Lancet 2024 modifiable risk factors

## Data sources (see `docs/data_sources.md`)

- Alzheimer's Association. **2024 Alzheimer's Disease Facts and Figures.** *Alzheimer's & Dementia* 20(5): 3708-3821.
- Matthews KA, et al. **Racial and ethnic estimates of Alzheimer's disease and related dementias in the United States.** *Alzheimer's & Dementia* 2019.
- CDC MMWR. **Racial and Ethnic Differences in Subjective Cognitive Decline.** 2023;72(10).
- Livingston G, et al. **Dementia prevention, intervention, and care: 2024 report of the Lancet standing Commission.** *The Lancet* 404(10452): 572-628.
- WHO. **Dementia fact sheet.** 2025.

## Running the project

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.ml.train_models   # Trains demo models on synthetic data
uvicorn app.main:app --reload
```

#### Configuration

All endpoints except `/`, `/health`, `/users/signup`, and `/users/login` require a
bearer token (`Authorization: Bearer <access_token>`) returned by signup/login, and
only ever expose the authenticated user's own data.

| Variable | Default | Notes |
| --- | --- | --- |
| `COGNISENSE_ENV` | `development` | `production` disables `/docs` and requires an explicit secret key and CORS allow-list |
| `COGNISENSE_SECRET_KEY` | random per process | JWT signing key; **required** in production |
| `COGNISENSE_TOKEN_TTL_MINUTES` | `60` | Access-token lifetime |
| `COGNISENSE_ALLOWED_ORIGINS` | localhost dev origins | Comma-separated CORS allow-list (no wildcards) |
| `COGNISENSE_MAX_AUDIO_BYTES` | `10485760` | Upload size cap for voice clips |
| `COGNISENSE_DB_PATH` | `backend/app/db/cognisense.db` | SQLite location |

### Desktop app
```bash
cd desktop_app
python main.py
```

### Mobile app
```bash
cd mobile_app
npm install
npx react-native run-android   # or run-ios
```
