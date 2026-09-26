# Changelog

All notable changes to CogniSense. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

CogniSense is a research and self-tracking tool, **not a medical diagnostic
device**. Its scoring models are demo models trained on synthetic data.

## [1.0.0] — 2026-09-26

The first release: a self-hostable backend, a web app that installs on phones,
and a desktop client.

### Features

- Daily morning, midday and evening check-ins. The evening test grades five
  image associations and the day's recalled activities into a daily cognitive
  score, using a PyTorch behavioral model.
- A risk report: the recent average and the change from the user's own
  baseline, each with a 95% bootstrap interval; an explicit "not enough to say
  yet" state; and age-, gender- and race-matched research benchmarks.
- A trend report with 14- and 30-day views: each day's score, the 95% interval
  on the 7-day average, the baseline, and gaps for missed days. It has a text
  summary, a table view and keyboard access.
- Memory support: saved intentions, recall checks, and a list that is always
  shown afterwards.
- Reminder notifications by Web Push, with quiet hours and a cooldown.
- Accounts: revocable sessions (an HttpOnly cookie for browsers, a bearer token
  for the desktop app), CSRF protection, throttled login, password change,
  recovery codes, and email recovery when SMTP is configured.
- A per-user time zone: the check-in day and quiet hours follow the user's
  local midnight and waking hours, including across DST changes.
- An installable web app (manifest, icons, Apple web-app tags). On iOS this is
  what makes push possible.
- A Tkinter desktop client.
- The validation harness `python -m app.ml.validate`: user-level nested CV with
  permuted-label, baseline and confound controls.
- Production deployment: a Docker image serving the API and the built web app
  from one origin, docker compose with a single reminder scheduler, a
  production config template that refuses to boot while unsafe, and CI that
  runs the tests, lint, build and a production-config Docker smoke test.

### Fixed during release preparation

- The desktop client never sent a session token after session auth arrived, and
  stored the whole login response as the user. It now holds the token and sends
  it on every request, returns to the login screen on a 401, and has a Log out
  button that revokes the session.
- The check-in day was a UTC day, which rolled over at 17:00 in Los Angeles.
- The risk report compared a period with itself when there was no earlier
  baseline, and reported "no change" instead of "not enough to say yet".
- The report showed a new account "your recent average: 0%", computed from no
  data, and counted a retaken evening test as another day of evidence.
- The evening test could be retaken. Each retake was scored, added to the
  check-in count behind every later score, and shown as the day's result. A
  second attempt is now answered with the first result (409), as the morning
  check-in already was.
- The web app remembered the morning check-in in the browser instead of
  asking the server, so on a new device the evening test said there was no
  morning check-in, and on a device last used yesterday it tested the evening
  against yesterday's cues.
- The web app signed out on any 401, so a wrong "current password" when
  changing it logged the person out; and on any failure of its start-up check,
  so did a server restart. It now signs out only once `/users/me` confirms the
  session is gone.
- The evening check-in stored and displayed a speech biomarker of 0.75 when no
  speech had been recorded.
- The site root answered with the API's JSON in production, so the bare domain
  and the installed app showed JSON instead of the app.
- Deployed, the web app could not reach its API. It calls `/api/...`, which
  only the development proxy understood; in production those calls fell
  through to the page (a GET got HTML, a POST a 405), so no one could even log
  in. The backend now answers under `/api` itself, and CI checks it in the
  container.
- The email-confirmation page could post its single-use token twice, then
  report a successful confirmation as expired.
- On a phone there was no way to log out or reach account settings.
- Web error messages showed raw JSON such as `{"detail":"Invalid credentials"}`.
- Signup said demographics never left the device (they are stored with the
  account) and allowed 6-character passwords (the server requires 8).
- The two production workers could crash the server on its first start. Both
  created the database tables at once, the loser failed with "table users
  already exists", and gunicorn stops everything when a worker fails to boot.
  Schema creation now runs under a lock.
- Behind docker compose, a reverse proxy's requests reach the app from the
  network gateway rather than 127.0.0.1. The compose subnet is now pinned, so
  the production template can trust that address, and the per-IP login throttle
  sees real clients instead of one shared address.
- Nine npm advisories, including an open redirect in react-router.

### Removed

- The React Native app, which had no native projects and could not run. The
  installable web app replaces it on phones.
- `users.utc_offset_minutes` is no longer used; the column is left in existing
  databases.
- Unused Vite template assets.

### Known limitations

- Clinical validity is unestablished: nothing in the project carries a
  clinical label.
- No client records speech yet; the speech model is used only for an uploaded
  recording.
- Notifications need the backend running.
- The association pictures are placeholders: each cue shows its object's
  name under a generic picture icon.

[1.0.0]: https://github.com/JackyJHung/cognisense/releases/tag/v1.0.0
