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
│   │   ├── notifications/       # Web Push: VAPID keys, sender, scheduler
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

### GPU (optional, NVIDIA only)

PyPI serves the **CPU-only** torch wheel on Windows, so the install above leaves
an NVIDIA card idle. To use it:

```bash
pip install -r requirements-cuda.txt
```

Verify:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`cu124` covers Ada (RTX 40-series), Ampere and Hopper, and needs driver 550+.
The CUDA toolkit does not need installing separately — the wheel bundles its own
runtime. Note that both shipped models are small and run fine on CPU; the GPU
matters when you retrain on a real corpus, and the ceiling there is VRAM.

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

## Authentication

Every route except signup, login and the VAPID public key requires a bearer
token. Signup and login return one:

```json
{ "user": {...}, "token": "s3cr3t...", "token_type": "bearer", "expires_at": "..." }
```

Send it as `Authorization: Bearer <token>`. It lasts 30 days.

**What this fixed.** Endpoints used to take `user_id` from the path or body and
trust it. `GET /reminders/4` returned user 4's reminders to anyone who asked —
their memory scores, check-ins and risk report, reachable by changing a digit in
a URL. `backend/tests/test_auth.py` now runs that exact attack as a fully
logged-in second user and asserts it fails.

Two separate checks, because authentication alone is not enough — an attacker
with their own valid account is still authenticated:

| Route shape | Check | Failure |
|---|---|---|
| `/reminders/{user_id}` | `require_self` — must be your own id | 403 |
| `/reminders/check/{check_id}` | `owned_or_404` — resource must be yours | 404 |
| `user_id` in a JSON body | `require_own_id` | 403 |

Resource routes answer **404**, not 403, so the reply does not confirm that
someone else's record id exists.

**Sessions are opaque tokens, not JWTs.** Only the SHA-256 of a token is stored,
so a leaked database yields nothing presentable to the API. Logout deletes the
row, which means it now actually works — previously it cleared localStorage and
the credential stayed valid indefinitely. `POST /users/logout` with
`{"all_devices": true}` revokes every session for the account.

**Still worth knowing:** tokens live in `localStorage`, which is readable by any
XSS on the origin. Moving them to an `HttpOnly` cookie would need CSRF
protection in exchange. There is no password-change or account-recovery flow,
and no rate limiting on login — brute-force protection is the next thing to add
if this ever leaves localhost.

## Notifications (`/push`)

Reminders arrive with the app closed, via Web Push. Turn them on from the
"Reminder notifications" card on the reminders page, then press **Send a test**
to confirm the chain works before relying on it.

How it fits together:

```
scheduler (in the FastAPI process, every 60s)
    -> is anything pending and due for this user?
    -> is it inside their waking hours?
    -> have they been pushed in the last 6h?
        -> pywebpush  ->  push service (FCM / Mozilla)  ->  service worker
                                                              -> notification
```

**What "closed" actually means.** Be precise about this, because the honest
answer is not "always":

| State | Notification arrives? |
|---|---|
| Tab closed | Yes — the service worker is woken by the push service |
| Browser closed, phone | Yes on Android; iOS needs the PWA added to the Home Screen (16.4+) |
| Browser closed, desktop | Only if the browser keeps a background process (Chrome: Settings → System → "Continue running background apps") |
| Backend stopped | No — the scheduler *is* the sender |

Three rules keep it from becoming spam: a cooldown (default 6h), quiet hours
taken from the user's own wake/sleep times, and nothing sent when there is
nothing due. The browser reports its UTC offset when it subscribes, because
`wake_time` and `sleep_time` are bare clock times with no zone attached — the
server would otherwise have no idea whether it is 3am for that person.

**The notification never names the items.** It says "You have 3 things saved",
never what they are. Naming them would hand over the answers to a recall test,
and would put someone's errands on a lock screen for anyone nearby to read.

Tuning, via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `COGNISENSE_PUSH_TICK_SECONDS` | `60` | how often the scheduler looks |
| `COGNISENSE_PUSH_COOLDOWN_HOURS` | `6` | minimum gap between pushes |
| `COGNISENSE_DISABLE_SCHEDULER` | unset | set to `1` to stop the loop (tests do) |
| `COGNISENSE_VAPID_SUBJECT` | `mailto:admin@cognisense.local` | contact in the VAPID JWT |
| `COGNISENSE_LOG_LEVEL` | `INFO` | `DEBUG` to trace scheduler decisions |

**The VAPID keypair must stay stable.** It is generated on first use at
`backend/app/db/vapid_private.pem` (gitignored) and reused forever. Regenerating
it silently breaks every existing subscription, because browsers pin the
`applicationServerKey` they subscribed with. Do not copy a development key to a
real deployment; generate a fresh one there and let subscribers re-register.

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

- **Recall matching is token overlap**, not meaning. "Ring the dentist" only
  matches "call the dentist about the crown" because "dentist" is a distinctive
  word; a paraphrase sharing no words would be scored as forgotten. Lemma
  matching or sentence embeddings would fix it, at the cost of a dependency the
  offline-first desktop client currently avoids.
- **Notifications need the backend running.** There is no delivery when the
  server is stopped — see the table above. A always-on host, or a native
  scheduled task, is what removes that constraint.
- **Per-user timezones.** The check-in "day" is a UTC day, so it rolls over at
  17:00 for a UTC-7 user. Push quiet hours *do* use the browser-reported offset;
  the check-in window does not, because the User model has no timezone field.
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
