import os
import pytest

# Set TESTING environment variable before any tests or imports are run
os.environ["TESTING"] = "1"
os.environ["USE_MOCK_VIDEO_API"] = "true"
os.environ["VIDEO_MAX_RETRIES"] = "2"
os.environ["VIDEO_MAX_ESTIMATED_COST_USD"] = "2.0"

from app.core.config import settings


@pytest.fixture(autouse=True)
def default_test_settings(monkeypatch):
    """Ensure tests run in isolated mock mode by default unless explicitly overridden."""
    monkeypatch.setattr(settings, "use_mock_video_api", True)
    monkeypatch.setattr(settings, "video_max_retries", 2)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 2.0)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    test_db_path = "data/test_app.db"
    # Ensure a clean slate for the test database
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass
    
    # Initialize DB tables for testing
    from app.db.database import init_db
    init_db()
    
    yield
    
    # Optional cleanup after tests
    # if os.path.exists(test_db_path):
    #     try:
    #         os.remove(test_db_path)
    #     except OSError:
    #         pass
