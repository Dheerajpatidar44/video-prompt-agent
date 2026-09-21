from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import api_router

setup_logging()

app = FastAPI(
    title=settings.app_name,
    description="AI Video Prompt Generation Agent Backend",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")
