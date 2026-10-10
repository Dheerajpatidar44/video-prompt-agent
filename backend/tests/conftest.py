import os
import pytest

# Set TESTING environment variable before any tests or imports are run
os.environ["TESTING"] = "1"

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
