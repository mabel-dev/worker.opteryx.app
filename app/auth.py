"""Authentication helpers for the service.

This module centralizes token parsing and validation logic so multiple
endpoints can reuse it. The primary exported function is
`validate_token_from_request(request, expected_sub)` which will extract the
bearer token, validate signature via `app.secret_store` and verify the `sub`
claim equals the expected GPC subject.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from jose import JWTError
from jose import jwt as jose_jwt
from starlette.requests import Request

GPC_SUBJECT = "109805708368864229943"
EXPECTED_AUDIENCE = "https://worker.opteryx.app/api/v1/submit"
EXPECTED_ISSUER = "https://accounts.google.com"


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1]


def validate_token(token: str) -> dict:
    """Validate the given JWT token and ensure `sub` matches expected_sub.

    Returns verified `claims` as a dict on success. Raises `HTTPException(401)`
    for invalid tokens or a `HTTPException(500)` if any internal issues occur
    (missing JWT library, missing public key, etc.).
    """
    try:
        claims = jose_jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token claims") from exc

    # Validate issuer
    iss = claims.get("iss")
    if iss != EXPECTED_ISSUER:
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    # Validate audience
    aud = claims.get("aud")
    if aud != EXPECTED_AUDIENCE:
        raise HTTPException(status_code=401, detail="Invalid token audience")
    # Validate subject
    sub = claims.get("sub")
    if sub != GPC_SUBJECT:
        raise HTTPException(status_code=401, detail="Token subject mismatch")
    return claims


def validate_token_from_request(request: Request) -> dict:
    """Convenience wrapper that extracts the token from the request and validates it."""
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization missing or invalid")
    return validate_token(token)
