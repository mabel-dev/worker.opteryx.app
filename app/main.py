import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from orso.logging import get_logger
from orso.logging import set_log_name

from app.middleware.audit import AuditMiddleware
from app.routes import router as routes_router

set_log_name("opteryx.worker")
logger = get_logger()
logger.setLevel(5)

application = FastAPI(title="Opteryx Worker", default_response_class=ORJSONResponse)
application.add_middleware(AuditMiddleware)

# include routes
application.include_router(routes_router)

__all__ = ["application"]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "main:application",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )
