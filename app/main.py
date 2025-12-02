from app.middleware.audit import AuditMiddleware
from app.routes import router as routes_router
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from orso.logging import get_logger
from orso.logging import set_log_name

set_log_name("opteryx.worker")
logger = get_logger()
logger.setLevel(5)

app = FastAPI(title="Opteryx Worker", default_response_class=ORJSONResponse)
app.add_middleware(AuditMiddleware)

# include routes
app.include_router(routes_router)

__all__ = ["app"]
