import uvicorn

if __name__ == "__main__":
    import os
    import sys
    
    # Ensure app directory is in path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from app.core.config import settings
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development")
    )
