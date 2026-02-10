from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse as HttpResponse

from app.auth import validate_token_from_request
from app.worker import process_statement

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.post("/submit", response_class=HttpResponse, status_code=202)
async def submit(request: Request, background_tasks: BackgroundTasks):
    claims = validate_token_from_request(request)
    sub = claims.get("sub")
    # Validate expected GPC subject
    if sub != "109805708368864229943":
        raise HTTPException(status_code=401, detail="Token subject mismatch")

    job = await request.json()
    execution_id = job.get("execution_id")
    
    if not execution_id:
        raise HTTPException(status_code=400, detail="Missing execution_id")

    # Process the statement in a background task to avoid blocking the event loop
    background_tasks.add_task(process_statement, execution_id)

    return


__all__ = ["router"]
