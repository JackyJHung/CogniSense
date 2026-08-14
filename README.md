# CogniSense

AI/ML application for early-risk screening of Alzheimer's disease and related dementias (ADRD) using speech patterns and behavioral biomarkers captured via microphone and camera. CogniSense delivers daily check-ins, image-association memory tasks, biweekly/monthly reports, and personalized prevention guidance grounded in peer-reviewed research.

> **Important:** CogniSense is a research and self-tracking tool. It is **NOT** a medical diagnostic device and does not replace professional evaluation. Any output from this app is a suggestion, not professional advice. If you or a loved one are experiencing worsening memory concerns, please consult a licensed physician or neurologist.

## Architecture

A **shared Python/PyTorch backend** (FastAPI + SQLite) serves three independent
clients, and everything that produces a number goes through a shared methodology
layer in `core/`.

```
cognisense-app/
├── core/                # Shared methodology layer (domain-agnostic)
│   ├── stats.py         #   MetricCI + bootstrap intervals
│   ├── splits.py        #   group-level nested CV (group = USER)
│   ├── pipelines.py     #   sklearn pipelines with preprocessing inside the fold
│   ├── evaluate.py      #   nested-CV evaluation -> out-of-fold predictions
│   ├── controls.py      #   permuted-label / baseline / confound checks
│   ├── qc.py            #   pass / flag / exclude record gates
│   ├── seeding.py       #   one seed for random, numpy and torch
│   ├── env.py           #   environment capture for report headers
│   └── report.py        #   contract-enforcing Markdown + JSON renderer
├── backend/             # FastAPI server + PyTorch ML models + SQLite DB
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── database.py          # SQLite setup
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── models/              # ORM models
│   │   ├── routes/              # API endpoints (users, check-ins, reports)
│   │   ├── ml/                  # PyTorch speech + behavioral models
│   │   │   ├── validate.py      #   validation harness (nested CV + controls)
│   │   │   └── text_features.py #   shared tokenisation / recall matching
│   │   ├── memory/              # prospective-memory checks — the memory aid
│   │   ├── reports/             # report templates
│   │   └── data/                # Research benchmarks (age/gender/race)
│   ├── tests/
│   └── requirements.txt
├── desktop_app/         # Python-only Tkinter desktop client (stdlib UI)
├── web_app/             # React + Vite + Tailwind + Framer Motion web client
├── mobile_app/          # React Native cross-platform (iOS + Android) scaffold
└── docs/                # Data sources, model cards, architecture notes
```

You can run either the **Python-only desktop** experience (Tkinter, no npm needed) or the **web client** (modern look, animated, requires Node). They are fully independent — pick whichever you prefer or run both side-by-side against the same backend.

### Where `core/` came from

`core/` is the part of a separate glioma diffusion-MRI research pipeline
(`C:\Users\jjhun\projects\cognisense`) that was worth keeping: the machinery for
producing a number you can defend. The tumour-specific stages — DWI loading,
lesion-aware registration, CSD, tractography, connectome construction — were
deliberately **not** merged. They are glioma-specific, they were never
implemented, and they serve none of this app's goals. That project is untouched
and still on disk.

What the merge actually bought:

| Before | After |
|---|---|
| bare point scores (`daily_score`, `pct_change`) | every user-facing number carries a 95% interval |
| warning fired on a fixed 20% threshold | warning requires the interval on the change to exclude zero |
| no distinction between "fine" and "can't tell yet" | explicit `inconclusive` state, surfaced in the UI |
| models never evaluated after training | `app.ml.validate` — nested CV + three negative controls |
| `set_seed()` covering numpy + torch only | `core.seeding.set_global_seed` also covers `random` and `PYTHONHASHSEED` |
| ad-hoc response dicts | contract-enforcing report renderer |

Two defects in the research code were fixed on the way in rather than carried
across:

- **The confound regression leaked.** It was fitted on all rows including the
  test fold, which biased the control toward passing. It is now fitted inside
  each training fold (`core/evaluate.py::_residualise_fold`).
- **The permuted-label control tested the wrong direction.** It required the
  interval to *cover* chance, so it reported the known negative bias of
  cross-validated AUC under the null as a failure. Leakage pushes permuted
  performance *above* chance; only that is now a failure.

A third limitation was closed: comparing two models used "the width of the
widest input CI" as a stand-in for a real interval on the difference.
`core.stats.paired_bootstrap_delta` resamples both models on the same rows
instead.

## Setup

The virtualenv and `node_modules` were intentionally not copied into this tree —
virtualenvs hard-code their own paths and break when moved. Recreate them:

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # PowerShell on Windows
pip install -r requirements.txt
python -m app.ml.train_models       # Trains demo models on synthetic data
uvicorn app.main:app --reload
```

### Web app (React + Tailwind + Framer Motion)
Requires Node.js LTS. Backend must be running on `localhost:8000`.
```bash
cd web_app
npm install
npm run dev          # http://localhost:5173
```
Override the backend URL with `VITE_BACKEND_URL` in `web_app/.env.local` if needed.

### Desktop app (Python-only — Tkinter)
No extra dependencies; uses the same `backend/.venv`.
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

## Validating the models

```bash
cd backend
python -m app.ml.validate
```

Runs the behavioral feature set through user-level nested CV, executes all three
negative controls, and writes a report to `backend/results/`. Needs only numpy,
scipy and scikit-learn — no torch, no audio stack.

**Read the first section of that report before quoting any number from it.** The
harness evaluates a *simulated* cohort with *simulated* labels, because
CogniSense has no ground truth: nobody in `cognisense.db` carries a clinical
diagnosis. It can tell you the pipeline is honest and that the features separate
the classes they were built to separate. It cannot tell you that a low CogniSense
score means anything about a real person's brain. Closing that gap needs a
labelled clinical corpus (DementiaBank Pitt, ADReSS, ADNI) under ethics
approval, and it is the single largest distance between this repository and a
defensible product claim.

## Tests

```bash
cd backend
python -m pytest tests -q
```

`tests/test_core_no_leakage.py` is the firewall: it fails if test-fold data ever
reaches training. It includes a direct demonstration — same data, same estimator,
split by row instead of by user — of how much AUC inflates when one person is
allowed to span a fold boundary.

## Memory support (`/reminders`)

The user saves things they mean to do — free text, an optional photo, an
optional due time. Later, a check fires: *"Without looking at your list, what
did you mean to do? Name at least one thing."* The recall is graded against the
list, then the list is shown, then they tick off what they actually did.

**The list is always shown, pass or fail.** This is a memory aid that happens to
measure, not a test that withholds. Withholding somebody's own reminders because
they failed to remember them would punish exactly the impairment the feature
exists to support, and would land hardest on the people who need it most.
`app/memory/prospective.py::should_show_aid` is a function rather than a setting
so that any future change to this has to be made deliberately, and
`test_the_list_is_shown_even_when_nothing_was_recalled` fails if it ever is.

Two things are recorded separately and deliberately: whether the intention was
**recalled**, and whether it was **done**. Forgetting that you meant to do
something is a different signal from remembering and not getting to it.

Matching is lenient by design — the chosen failure mode is a false pass, since
wrongly telling someone they forgot something they did remember is the more
harmful error. An item counts as recalled if the recall covers 60% of its
content words *or* names a word unique to that item on the current list. The
second rule matters: without it, "call the dentist about the crown" would score
a user who said "the dentist" as having forgotten it, so writing a careful
description would make an item harder to recall.

Prospective recall rate is reported through `core.stats` like everything else —
with a 95% interval, and no trend claim until there are enough checks.

**Scheduling note:** a server cannot raise a pop-up. `GET /reminders/{id}/due`
reports what is outstanding; the web client polls it and React Native would
schedule a local notification. Nothing here pushes.

## Core feature set (Phase 1 — this build)

1. **Onboarding** — age, gender, race/ethnicity, wake time, sleep time
2. **Morning check-in** — record today's plans + present 5 image associations
3. **Midday check-in** — light recall prompt
4. **Evening check-in** — recall today's activities + test image associations
5. **Speech biomarker capture** — record short voice sample, extract MFCC features, score with PyTorch 1D-CNN
6. **Behavioral biomarker scoring** — recall accuracy, response latency, linguistic features → PyTorch MLP
7. **Research-grounded risk comparison** — user scores against age/gender/race benchmarks, now with intervals and an explicit inconclusive state
8. **Safety layer** — every report, warning, and suggestion carries the non-diagnostic disclaimer

## Phase 2 (next)

- **Real notification delivery.** The reminder check exists and the `/due`
  endpoint reports what is outstanding, but nothing pushes yet — the web client
  has to be open and polling. Needs a service worker for web and
  local notifications for React Native.
- **Recall matching is token overlap**, not meaning. "Ring the dentist" does not
  match "call the dentist" unless the distinctive word carries it. Lemma
  matching or sentence embeddings would fix this; both add a dependency the
  offline-first desktop client currently avoids.
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
