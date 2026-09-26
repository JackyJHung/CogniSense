# CogniSense

AI/ML application for early-risk screening of Alzheimer's disease and related dementias (ADRD) using speech patterns and behavioral biomarkers captured via microphone and camera. CogniSense delivers daily check-ins, image-association memory tasks, biweekly/monthly reports, and personalized prevention guidance grounded in peer-reviewed research.

> **Important:** CogniSense is a research and self-tracking tool. It is **NOT** a medical diagnostic device and does not replace professional evaluation. Any output from this app is a suggestion, not professional advice. If you or a loved one are experiencing worsening memory concerns, please consult a licensed physician or neurologist.

## Architecture

A **shared Python/PyTorch backend** (FastAPI + SQLite) serves two independent
clients — a web app that installs to a phone's Home Screen, and a Tkinter desktop
app — and everything that produces a number goes through a shared methodology
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
├── web_app/             # React + Vite + Tailwind web client; installable (PWA)
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
No extra dependencies; uses the same `backend/.venv`. The backend must be
running; point the app elsewhere with `COGNISENSE_BACKEND` (default
`http://127.0.0.1:8000`).
```bash
cd desktop_app
python main.py
```
It authenticates with the bearer token from login, held in memory only, so
closing the app discards it and **Log out** revokes it on the server. When a
session ends — idle expiry, a password change, or "sign out everywhere" on
another device — the next action returns to the login screen and says why.
All HTTP goes through `desktop_app/api_client.py`, which
`backend/tests/test_desktop_client.py` drives against the real API.

### On a phone: install the web app
There is no separate mobile app. The web client ships a manifest
(`web_app/public/manifest.webmanifest`) and icons, so it installs to the Home
Screen and opens full-screen like a native app. Installing needs HTTPS — a
deployed server; `localhost` also counts, for development.

- **iPhone / iPad (Safari):** Share → **Add to Home Screen**. On iOS this is
  what makes reminders possible at all: Safari delivers web push only to a web
  app on the Home Screen (iOS 16.4+), so turn notifications on from inside the
  installed app.
- **Android (Chrome):** menu → **Install app**, or accept the install prompt.
- **Desktop (Chrome, Edge):** the install button in the address bar.

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

### Where the session lives

Browsers get an **HttpOnly cookie** — script cannot read it, so an XSS on the
origin can no longer walk off with a 30-day credential. The native client, the
desktop app, keeps using `Authorization: Bearer`: its HTTP session refuses
cookies, so the token is the only credential it ever sends.

A cookie is attached automatically, which is CSRF. Three layers answer that:

1. **`SameSite=Strict`** — the browser will not attach it to any cross-site
   request at all.
2. **Double-submit token** — a second, deliberately *readable* cookie, echoed
   back in `X-CSRF-Token`. An attacking origin can cause the session cookie to
   be sent but cannot read the other one, so it cannot produce the header. A
   cross-origin HTML form cannot set custom headers at all.
3. **Origin check** on state-changing requests.

Enforced in middleware (`app/csrf.py`), not per-route, because the usual way
CSRF protection fails is that someone adds an endpoint and forgets.

Bearer-authenticated requests skip the CSRF check: a browser never attaches an
`Authorization` header to a forged cross-site request, so they are immune by
construction.

**Why `/api` is proxied.** A `SameSite=Strict` cookie set by `127.0.0.1:8000` is
never sent to a page on `localhost:5173` — different sites. Weakening it to
`SameSite=None` would re-open the exact hole the cookie exists to close. Instead
Vite proxies `/api` to the backend in development, and the backend serves
`web_app/dist` itself in production, so the browser sees one origin either way.
Relatedly, the old CORS config (`allow_origins=["*"]` with
`allow_credentials=True`) was not merely loose — browsers refuse to send cookies
to a wildcard origin, so it would have broken cookie auth outright.

### Brute-force protection

Login, signup, password change and recovery are throttled per-username and
per-IP: 5 failures per user or 20 per address in a 15-minute window, then a
lockout that escalates 1m → 2m → 4m, capped at an hour.

The check runs **before** any password hashing. bcrypt costs ~250ms of pinned
CPU, so a limit applied after verification would leave the endpoint a
denial-of-service amplifier — a handful of attackers sending junk could
saturate the processor without guessing anything. The timing-equaliser hash
(which stops username enumeration by response time) makes that worse, not
better, since junk requests then pay the bcrypt cost too. Ordering is the whole
defence, and `test_throttle_refuses_before_any_password_hashing` asserts it.

Each surface has its **own** throttle namespace. Sharing them would mean that
someone who forgot their password, failed login a few times, and reached for
account recovery would find recovery locked as well — the one route back into
the account barred at exactly the moment it was needed, by their own honest
attempts.

Tuning: `COGNISENSE_*` variables are read at import; see `app/ratelimit.py`.

### Password change and account recovery

`POST /users/password` takes the current and new password, then revokes **every**
session and issues one fresh one. That is the point of changing a password after
a suspected compromise: whoever holds a stolen token must lose it.

There are **two** recovery routes, and a user can have either or both.

**Recovery codes** work with no infrastructure at all. Ten single-use codes are
issued at once, shown once, and stored only as hashes — CogniSense cannot tell a
user what their codes were, only issue new ones. Generating a new set cancels
every unused old one. Codes avoid `0/O/1/I/L` and ignore case and dashes on
entry: they get copied off a screen by hand, often by somebody already worried
about their memory.

**Email reset links** work when SMTP is configured. The address must be
**confirmed first**, and that is the point rather than a formality: an
unverified address is worse than none, because a typo at signup would send reset
links to a stranger's inbox and turn recovery into account takeover. So an
address is unusable for reset until a confirmation link is clicked, and changing
the address drops verification again.

Adding or changing the address requires the current password — otherwise a
borrowed unlocked device could point recovery at someone else's inbox and
convert temporary access into permanent ownership.

`POST /recovery/forgot` always returns the same message, whether the account
exists, has an email, or has confirmed it. On a cognitive-health app,
confirming that a given address has an account is itself a disclosure. It is
throttled too, or it would be a free unlimited probe for which accounts exist.

Reset links expire in 60 minutes, work once, are superseded when a new one is
requested, and die if the account's address changes afterwards — a link mailed
to an inbox somebody has since lost control of must not stay live. A successful
reset by either route revokes every session.

**With no SMTP configured the flow still runs**: `app/emailer.py` writes each
message, link included, to the server log instead of sending, and the UI says
"this server has no mail configured" rather than telling someone to check an
inbox that will stay empty.

**Still worth knowing.** A user who loses their password, their codes, *and*
access to their confirmed email cannot be recovered — at that point nothing is
left that proves the account is theirs.

## Configuration and deployment

Everything environment-driven lives in `backend/app/config.py`, with a
documented template at `backend/.env.example`. Nothing is required for local
development; every default is tuned for `http://localhost`.

```bash
cp backend/.env.example backend/.env      # then edit
uvicorn app.main:app --env-file .env
```

**A production deploy that is misconfigured refuses to start.** With
`COGNISENSE_ENV=production`, `config.validate()` raises on boot if cookies are
not `Secure`, if the allowed origins are empty, still contain `localhost`, or
are plain `http://`, or if the VAPID subject is still the placeholder. Failing
closed is deliberate: a warning in a log scrolls past and the server keeps
serving, which is precisely how an insecure deploy survives. In development the
same list is only logged, so a developer sees what would break a deploy without
being blocked.

The startup log prints the active configuration, so the security posture is
visible rather than assumed:

```
config environment        development
config cookie_secure      False
config allowed_origins    ['http://localhost:5173', ...]
config trusted_proxies    none (X-Forwarded-For ignored)
config session_idle_days  7
```

| Variable | Default | Notes |
|---|---|---|
| `COGNISENSE_ENV` | `development` | `production` makes the startup check fatal |
| `COGNISENSE_COOKIE_SECURE` | on in production | must be off for plain-http local dev |
| `COGNISENSE_ALLOWED_ORIGINS` | dev origins | CORS **and** the CSRF Origin check |
| `COGNISENSE_TRUSTED_PROXIES` | *(empty)* | see below — empty is the safe default |
| `COGNISENSE_SESSION_TTL_DAYS` | `90` | absolute cap; must exceed the idle window |
| `COGNISENSE_SESSION_IDLE_DAYS` | `30` | idle expiry — see below, tuned for this app |
| `COGNISENSE_VAPID_SUBJECT` | placeholder | rejected in production |
| `COGNISENSE_PUBLIC_URL` | `http://localhost:5173` | links in emails are built from it |
| `COGNISENSE_SMTP_HOST` | *(empty)* | empty = log emails instead of sending |
| `COGNISENSE_SMTP_FROM` | placeholder | must be deliverable or mail is spam-filed |
| `COGNISENSE_LOG_LEVEL` | `INFO` | `DEBUG` traces scheduler decisions |

**`X-Forwarded-For` is ignored unless a trusted proxy is configured.** It used
to be believed whenever present — and since any client can set a header, sending
a different value each request bought a fresh per-IP rate-limit budget every
time, making the address limit decorative. Now the header is read only when the
direct peer is listed in `COGNISENSE_TRUSTED_PROXIES`; with none set, the socket
address is always used. Set it to the address the proxy connects *from*
(`127.0.0.1` for nginx on the same host), and make the proxy strip inbound
`X-Forwarded-For`, or a client can still prepend a forged entry.

**Sessions expire on idle as well as absolutely**, and the idle window is the
one that binds: 30 days idle inside a 90-day absolute cap. Active use refreshes
the clock on every request.

Thirty is deliberately not the usual seven. CogniSense's users are tracking
cognitive decline, and somebody who misses a week is precisely the person least
able to recall a password on being logged out — a short idle timeout lands
hardest on the users the app exists for, and the likely result is that they stop
using it rather than that they log back in. Thirty days absorbs an illness or a
hospital stay while still closing the window on a device that is genuinely gone.

The idle window **must** stay below the absolute cap, or it can never fire and
becomes a silent no-op; startup rejects that combination.

### Deploying

`backend/.env.production.example` is a filled-in template. Copy it and replace
`cognisense.example` with your domain — that substitution is the only edit
required:

```bash
cp backend/.env.production.example backend/.env
# replace cognisense.example throughout, then:
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

A half-finished copy fails at boot rather than serving. In particular, leaving
the placeholder domain in place is rejected: `.example`, `.invalid`, `.test` and
`.localhost` are reserved by RFC 2606 / 6761 and can never resolve, so one
appearing in production config always means an unreplaced placeholder — and
without the check the server would start and mail reset links to a domain nobody
owns.

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
| Browser closed, Android | Yes |
| iPhone / iPad | Only from the installed web app: Safari → Share → **Add to Home Screen** (iOS 16.4+), then turn notifications on inside it — see [installing on a phone](#on-a-phone-install-the-web-app) |
| Browser closed, desktop | Only if the browser keeps a background process (Chrome: Settings → System → "Continue running background apps") |
| Backend stopped | No — the scheduler *is* the sender |

Three rules keep it from becoming spam: a cooldown (default 6h), quiet hours
taken from the user's own wake/sleep times, and nothing sent when there is
nothing due. `wake_time` and `sleep_time` are bare clock times, so quiet hours
are placed in the user's [time zone](#time-zones) — the same one their check-in
day follows — or the server would have no idea whether it is 3am for them.

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

## Time zones

Each account has an IANA time zone (`users.timezone`, e.g. `America/Los_Angeles`).
The check-in day turns over at midnight there — one morning check-in per local
day, and "today's" morning is today's for the user, not for UTC. Push quiet
hours use the same zone, so there is one source of truth. A zone name rather
than a UTC offset, because an offset is an hour wrong for half of every year
wherever clocks change; day windows are 23 or 25 hours long on DST days.

| When | What happens to the zone |
|---|---|
| Signup | Set from the device: the browser's `Intl.DateTimeFormat().resolvedOptions().timeZone`, or the desktop's ICU / `/etc/localtime` |
| Login, or turning on notifications | Filled in **only if the account has none** — never overwritten, so a trip or a borrowed laptop cannot move someone's day |
| Settings page | Changed deliberately; offers "use this device's zone" when they differ |

Unknown names are refused with a 422 at signup and in Settings, and ignored at
login — a strange value from a browser must never stop someone logging in.
Accounts created before zones existed have none (`NULL`), which is counted as
UTC, exactly as before; the web app fills it in from the device the next time
it opens. `tzdata` is in `requirements.txt` because Windows has no system zone
database of its own.

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
- Attention warning triggered by sustained deviation from benchmarks
- Alarm-lock mode (phone unlocks only on check-in completion)
- Research-backed daily activity recommendations driven by the 14 Lancet 2024 modifiable risk factors

## Data sources (see `docs/data_sources.md`)

- Alzheimer's Association. **2024 Alzheimer's Disease Facts and Figures.** *Alzheimer's & Dementia* 20(5): 3708-3821.
- Matthews KA, et al. **Racial and ethnic estimates of Alzheimer's disease and related dementias in the United States.** *Alzheimer's & Dementia* 2019.
- CDC MMWR. **Racial and Ethnic Differences in Subjective Cognitive Decline.** 2023;72(10).
- Livingston G, et al. **Dementia prevention, intervention, and care: 2024 report of the Lancet standing Commission.** *The Lancet* 404(10452): 572-628.
- WHO. **Dementia fact sheet.** 2025.
