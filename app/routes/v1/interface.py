from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from app.auth import validate_token_from_request

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.post("/submit")
async def submit(request: Request):
    """Minimal stub: accept and echo job reference.

    This endpoint requires a signed JWT in the Authorization header and validates
    the token's signature and `sub` claim. The expected `sub` value for a GPC
    signed token is `109805708368864229943`.
    """
    claims = validate_token_from_request(request)
    sub = claims.get("sub")
    # Validate expected GPC subject
    if sub != "109805708368864229943":
        raise HTTPException(status_code=401, detail="Token subject mismatch")

    job = await request.json()
    return {"accepted": True, "job": job.get("statementHandle"), "jwt_sub": sub}


__all__ = ["router"]
