from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_name: str = Field("Video Prompt Agent", validation_alias="APP_NAME")
    app_env: str = Field("development", validation_alias="APP_ENV")
    app_host: str = Field("127.0.0.1",validation_alias="APP_HOST")
    app_port: int = Field(8000, validation_alias="APP_PORT")
    ollama_base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("qwen2.5:3b-instruct-q4_K_M", validation_alias="OLLAMA_MODEL")
    ollama_keep_alive: str = Field("30m", validation_alias="OLLAMA_KEEP_ALIVE")
    ollama_num_ctx: int = Field(8192, validation_alias="OLLAMA_NUM_CTX")
    ollama_num_predict: int = Field(2048, validation_alias="OLLAMA_NUM_PREDICT")
    ollama_temperature: float = Field(0.3, validation_alias="OLLAMA_TEMPERATURE")
    ollama_warmup_enabled: bool = Field(True, validation_alias="OLLAMA_WARMUP_ENABLED")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    
    # System Defaults for safe fields
    default_duration_seconds: int = Field(10, validation_alias="DEFAULT_DURATION_SECONDS")
    default_aspect_ratio: str = Field("16:9", validation_alias="DEFAULT_ASPECT_RATIO")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
