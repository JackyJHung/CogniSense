# Shared base: dependencies, application code, and demo model checkpoints.
FROM python:3.10-slim AS base

# libsndfile is required by librosa/soundfile for reading uploaded audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# CPU-only torch keeps the image several GB smaller than the default CUDA wheels.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        torch==2.5.1 torchaudio==2.5.1 \
    && pip install -r requirements.txt

COPY app ./app

# Bake the demo checkpoints into the image; without them speech scoring returns
# null and behavioral scoring falls back to a heuristic at runtime.
RUN python -m app.ml.train_models


# Test image: `docker build --target test -t cognisense-backend-test .`
FROM base AS test
RUN pip install -r requirements-dev.txt
COPY tests ./tests
CMD ["pytest", "tests/", "--cov=app", "--cov-report=term-missing"]


# Default target: the API server.
FROM base AS runtime

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
