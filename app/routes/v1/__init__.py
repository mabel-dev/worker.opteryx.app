from fastapi import APIRouter

from .interface import router as interface_router

router = APIRouter()
router.include_router(interface_router)
