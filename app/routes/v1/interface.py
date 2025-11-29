from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from app.auth import validate_token_from_request

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.post("/submit")
async def submit(request: Request):
    """
    Accept job
    """
    claims = validate_token_from_request(request)
    sub = claims.get("sub")
    # Validate expected GPC subject
    if sub != "109805708368864229943":
        print("sub mismatch:", sub)
        raise HTTPException(status_code=401, detail="Token subject mismatch")

    job = await request.json()
    return {"accepted": True, "job": job.get("statementHandle"), "jwt_sub": sub}


__all__ = ["router"]
