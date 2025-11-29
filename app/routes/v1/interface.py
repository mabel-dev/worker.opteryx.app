from fastapi import APIRouter
from fastapi import Request

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.post("/submit")
async def submit(request: Request):
    """Minimal stub: accept and echo job reference."""
    job = await request.json()
    return {"accepted": True, "job": job.get("statementHandle")}


__all__ = ["router"]
