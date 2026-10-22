from app.core.config import Settings
import os

def test_config_loads_defaults():
    # Test that default settings load when no env vars are present
    # We remove any env vars that might interfere
    old_env = dict(os.environ)
    for key in ["APP_NAME", "APP_ENV", "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"]:
        if key in os.environ:
            del os.environ[key]
            
    # Instantiate without loading from the .env file to test raw defaults.
    # anthropic_api_key is a required field without a default, so we must provide it
    # explicitly to test the defaults of the other fields.
    settings = Settings(_env_file=None, anthropic_api_key="dummy-key-for-test")
    assert settings.app_name == "Video Prompt Agent"
    assert settings.app_env == "development"
    assert settings.anthropic_model == "claude-sonnet-5"
    assert settings.anthropic_api_key == "dummy-key-for-test"
    
    # Restore env
    os.environ.clear()
    os.environ.update(old_env)


def test_google_api_key_optional_and_hidden_in_repr():
    settings = Settings(_env_file=None, anthropic_api_key="dummy-key-for-test", google_api_key="super_secret_key_999")
    assert settings.google_api_key.get_secret_value() == "super_secret_key_999"
    # Key must NOT appear in repr
    assert "super_secret_key_999" not in repr(settings)
    assert "super_secret_key_999" not in repr(settings.google_api_key)

    # Loads fine without GOOGLE_API_KEY provided (defaults to blank SecretStr)
    settings_no_key = Settings(_env_file=None, anthropic_api_key="dummy-key-for-test")
    assert settings_no_key.google_api_key.get_secret_value() == ""

