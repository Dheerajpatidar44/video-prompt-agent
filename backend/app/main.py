from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import api_router


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for FastAPI."""
    yield
    from app.llm.claude_client import LLMService
    await LLMService.close()


app = FastAPI(
    title=settings.app_name,
    description="AI Video Prompt Generation Agent Backend",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
