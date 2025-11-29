# Data Service

Purpose
- Resource API (Opteryx) that validates incoming JWTs against the Auth service JWKS.

Local run
- `make run` starts this service on `DATA_PORT` (default `8000`).
- Or from repo root:
  - `uvicorn data.main:app --reload --host 0.0.0.0 --port 8000`

Build (Docker / Cloud Build)
- Built by Cloud Build using `data/pyproject.toml` and `data/Dockerfile`.
- To build locally from repo root:
  - `docker build -f data/Dockerfile -t gcr.io/$PROJECT_ID/opteryx-data .`

Auth verification
- Uses `data/auth/deps.py` to verify incoming JWTs. Verification first attempts to use the local `data/app/secret_store` (`kid` key lookup), and falls back to fetching JWKS from `AUTH_URL` by `kid` header if a local key cannot be found.
- Checks signature, expiry (`exp` and `nbf`), and issuer (`iss`). The expected audience is `DATA_AUDIENCE` (defaults to `opteryx-api`).

Env
- `AUTH_URL` — URL of the auth service (default `http://localhost:8081` when running locally).
- `DATA_AUDIENCE` — expected `aud` claim for tokens (defaults to `opteryx-api`).
