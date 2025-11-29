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
from starlette.requests import Request

import app.secret_store as secret_store

try:
    from jose import JWTError
    from jose import jwt as jose_jwt
except Exception as exc:  # pragma: no cover - handled in code paths that call this module
    raise RuntimeError("JWT support is required") from exc


GPC_SUBJECT = "109805708368864229943"


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1]


def validate_token(token: str, expected_sub: str = GPC_SUBJECT) -> dict:
    """Validate the given JWT token and ensure `sub` matches expected_sub.

    Returns verified `claims` as a dict on success. Raises `HTTPException(401)`
    for invalid tokens or a `HTTPException(500)` if any internal issues occur
    (missing JWT library, missing public key, etc.).
    """
    try:
        header = jose_jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token header") from exc

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing kid header")

    pub_pem = secret_store.load_public_key(kid)
    if not pub_pem:
        raise HTTPException(status_code=401, detail="Public key not found for kid")

    try:
        claims = jose_jwt.decode(
            token, pub_pem, algorithms=["RS256"], options={"verify_aud": False}
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token signature or claims") from exc

    sub = claims.get("sub")
    if sub != expected_sub:
        raise HTTPException(status_code=401, detail="Token subject mismatch")
    return claims


def validate_token_from_request(request: Request, expected_sub: str = GPC_SUBJECT) -> dict:
    """Convenience wrapper that extracts the token from the request and validates it."""
    token = _extract_bearer_token(request)
    print("extracted token:", token)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization missing or invalid")
    return validate_token(token, expected_sub=expected_sub)
