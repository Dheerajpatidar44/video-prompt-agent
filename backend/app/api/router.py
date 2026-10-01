from fastapi import APIRouter
from app.api.routes import health, scripts, projects

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(scripts.router, prefix="/scripts", tags=["scripts"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
