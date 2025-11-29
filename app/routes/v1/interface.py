from fastapi import FastAPI, Request
from fastapi import HTTPException
from pydantic import BaseModel

app = FastAPI(title="Opteryx Worker")



@app.post("/api/v1/submit")
async def submit(request: Request):
    job = await request.json()
    # Minimal stub: accept and echo job reference.

    return {"accepted": True, "job": job.get("statementHandle")}
