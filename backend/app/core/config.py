from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_name: str = Field("Video Prompt Agent", validation_alias="APP_NAME")
    app_env: str = Field("development", validation_alias="APP_ENV")
    app_host: str = Field("127.0.0.1",validation_alias="APP_HOST")
    app_port: int = Field(8000, validation_alias="APP_PORT")
    ollama_base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("llama3", validation_alias="OLLAMA_MODEL")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    
    # System Defaults for safe fields
    default_duration_seconds: int = Field(10, validation_alias="DEFAULT_DURATION_SECONDS")
    default_aspect_ratio: str = Field("16:9", validation_alias="DEFAULT_ASPECT_RATIO")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
