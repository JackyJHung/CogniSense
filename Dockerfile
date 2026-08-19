# CogniSense — production image.
#
# Two stages: node builds the frontend, python runs everything. The frontend
# build is not optional. web_app/dist is gitignored, so a clean checkout has no
# built assets, and the backend's SPA mount only registers when that directory
# exists — skip this stage and the API answers fine while every page 404s.
#
# Serves ONE origin: the API and the built frontend come from the same
# container, which is what lets the session cookie be SameSite=Strict. See
# backend/app/csrf.py.

# ---------------------------------------------------------------------------
# Stage 1 — frontend
# ---------------------------------------------------------------------------
FROM node:20-slim AS web

WORKDIR /build

# Lockfile first so `npm ci` is cached until dependencies actually change.
COPY web_app/package.json web_app/package-lock.json ./
RUN npm ci

COPY web_app/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries, limited to what the imports genuinely pull in:
#
#   libsndfile1  soundfile, which librosa uses to read audio
#   ffmpeg       librosa's audioread fallback. NOT optional: browsers record
#                via MediaRecorder as webm/opus, which libsndfile cannot
#                decode, so every real voice sample takes this path
#   curl         the HEALTHCHECK below
#
# Deliberately absent: build-essential and any -dev headers. Every dependency
# here ships manylinux wheels, so nothing is compiled at install time and a
# compiler in the final image is just attack surface.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libsndfile1 \
      ffmpeg \
      curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python dependencies -----------------------------------------------------
# torch is installed FIRST and explicitly from the CPU index. requirements.txt
# alone would resolve the default wheel, which bundles the CUDA runtime: ~2.5GB
# of image for hardware a VM does not have. The CPU wheel is ~200MB and this app
# does inference on two small models, where CPU is entirely adequate.
COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --index-url https://download.pytorch.org/whl/cpu \
      "torch==2.5.1" "torchaudio==2.5.1" \
 && pip install -r backend/requirements.txt

# --- Application -------------------------------------------------------------
COPY core/ ./core/
COPY backend/ ./backend/
COPY --from=web /build/dist ./web_app/dist

# Train the demo models into the image. Checkpoints are gitignored, and without
# them the evening scoring path silently falls back to a heuristic — the app
# still answers, it just stops using the model it claims to use. Baking them in
# makes the image self-contained and the behaviour honest.
#
# These are DEMO models fitted to synthetic data. See backend/app/ml/validate.py
# for what that does and does not establish.
RUN cd backend && PYTHONPATH=/app:/app/backend python -m app.ml.train_models

# --- Runtime user ------------------------------------------------------------
# Non-root, and it owns only what must be writable at runtime:
#   backend/db          SQLite database
#   backend/app/db      uploaded audio, reminder photos, the VAPID private key
# Both are mount points for volumes in production; the chown covers the case
# where they are not mounted.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 cognisense \
 && mkdir -p /app/backend/db /app/backend/app/db \
 && chown -R cognisense:cognisense /app/backend/db /app/backend/app/db

USER cognisense

ENV PYTHONPATH=/app:/app/backend \
    COGNISENSE_ENV=production
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# UvicornWorker, not the default sync worker. This is an ASGI app; plain
# gunicorn workers cannot serve it and would fail on the first request.
#
# 2 workers means 2 resident copies of torch, so size the VM for roughly
# 1.5-2GB. It also means 2 scheduler loops unless they are disabled here — the
# compose file sets COGNISENSE_DISABLE_SCHEDULER=1 on this service and runs
# app.scheduler_main once, separately. See backend/app/scheduler_main.py.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
