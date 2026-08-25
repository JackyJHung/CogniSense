# CogniSense
Python toolkit for local, phone-style early Alzheimer’s risk screening from speech (+optional video); trains calibrated models; not diagnostic.

///Note: this is currently still being worked on and has no set end date as of now.

## Quick start (Docker)

```bash
docker compose up --build          # API on http://localhost:8000 (Swagger UI at /docs)
docker compose run --rm tests      # unit + API tests with coverage
```

See [cognisense/README.md](cognisense/README.md) for the full setup, including
running the backend without Docker and the desktop/mobile clients.
