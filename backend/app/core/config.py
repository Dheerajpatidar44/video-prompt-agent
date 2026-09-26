from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_name: str = Field("Video Prompt Agent", validation_alias="APP_NAME")
    app_env: str = Field("development", validation_alias="APP_ENV")
    app_host: str = Field("127.0.0.1",validation_alias="APP_HOST")
    app_port: int = Field(8000, validation_alias="APP_PORT")
    anthropic_api_key: str = Field(..., validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-5", validation_alias="ANTHROPIC_MODEL")
    anthropic_max_tokens: int = Field(2048, validation_alias="ANTHROPIC_MAX_TOKENS")
    anthropic_temperature: float = Field(0.3, validation_alias="ANTHROPIC_TEMPERATURE")
    anthropic_max_concurrency: int = Field(3, validation_alias="ANTHROPIC_MAX_CONCURRENCY")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    
    # System Defaults for safe fields
    default_duration_seconds: int = Field(10, validation_alias="DEFAULT_DURATION_SECONDS")
    default_aspect_ratio: str = Field("16:9", validation_alias="DEFAULT_ASPECT_RATIO")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
