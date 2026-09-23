from app.core.config import Settings
import os

def test_config_loads_defaults():
    # Test that default settings load when no env vars are present
    # We remove any env vars that might interfere
    old_env = dict(os.environ)
    for key in ["APP_NAME", "APP_ENV", "OLLAMA_MODEL"]:
        if key in os.environ:
            del os.environ[key]
            
    # Instantiate without loading from the .env file to test raw defaults
    settings = Settings(_env_file=None)
    assert settings.app_name == "Video Prompt Agent"
    assert settings.app_env == "development"
    assert settings.ollama_model == "llama3"
    
    # Restore env
    os.environ.clear()
    os.environ.update(old_env)
