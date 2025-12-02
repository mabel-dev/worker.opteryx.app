from app.auth import validate_token_from_request
from app.worker import process_statement
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import ORJSONResponse

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.post("/submit", response_class=ORJSONResponse)
async def submit(request: Request):
    """
    Accept a job and return a response payload. The response includes an
    `audit` key which is an ORJSON-serializable object the middleware will
    parse and include in the audit log.
    """
    claims = validate_token_from_request(request)
    sub = claims.get("sub")
    # Validate expected GPC subject
    if sub != "109805708368864229943":
        raise HTTPException(status_code=401, detail="Token subject mismatch")

    job = await request.json()

    # Process the statement (may be monkeypatched in tests)
    execution_summary = process_statement(job.get("execution_id"))

    return execution_summary


__all__ = ["router"]
