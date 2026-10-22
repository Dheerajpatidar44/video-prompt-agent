from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Literal

class Settings(BaseSettings):
    app_name: str = Field("Video Prompt Agent", validation_alias="APP_NAME")
    app_env: str = Field("development", validation_alias="APP_ENV")
    app_host: str = Field("127.0.0.1", validation_alias="APP_HOST")
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

    # Cloudinary Config
    cloudinary_cloud_name: str = Field("default", validation_alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field("default", validation_alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field("default", validation_alias="CLOUDINARY_API_SECRET")

    # Video Generation Config
    use_mock_video_api: bool = Field(True, validation_alias="USE_MOCK_VIDEO_API")
    video_generation_concurrency_limit: int = Field(3, validation_alias="VIDEO_GENERATION_CONCURRENCY_LIMIT")
    video_poll_interval_seconds: int = Field(10, validation_alias="VIDEO_POLL_INTERVAL_SECONDS")
    video_max_retries: int = Field(2, validation_alias="VIDEO_MAX_RETRIES")

    # Veo 3.1 Lite / Google GenAI Config
    video_provider: str = Field("veo", validation_alias="VIDEO_PROVIDER")
    google_api_key: SecretStr = Field(SecretStr(""), validation_alias="GOOGLE_API_KEY")
    google_cloud_project: str = Field("", validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field("us-central1", validation_alias="GOOGLE_CLOUD_LOCATION")
    veo_model: str = Field("veo-3.1-fast-generate-001", validation_alias="VEO_MODEL")
    veo_resolution: Literal["720p", "1080p"] = Field("720p", validation_alias="VEO_RESOLUTION")
    veo_person_generation: str = Field("", validation_alias="VEO_PERSON_GENERATION")
    veo_negative_prompt_mode: Literal["drop", "append"] = Field("drop", validation_alias="VEO_NEGATIVE_PROMPT_MODE")
    veo_max_prompt_tokens: int = Field(1000, validation_alias="VEO_MAX_PROMPT_TOKENS")

    # Cost / safety guards (apply to real providers only, never to the mock)
    video_job_max_wait_seconds: int = Field(900, validation_alias="VIDEO_JOB_MAX_WAIT_SECONDS")
    video_status_max_consecutive_errors: int = Field(20, validation_alias="VIDEO_STATUS_MAX_CONSECUTIVE_ERRORS")
    video_max_shots_per_project: int = Field(10, validation_alias="VIDEO_MAX_SHOTS_PER_PROJECT")
    video_max_total_seconds_per_project: int = Field(40, validation_alias="VIDEO_MAX_TOTAL_SECONDS_PER_PROJECT")
    video_max_estimated_cost_usd: float = Field(5.0, validation_alias="VIDEO_MAX_ESTIMATED_COST_USD")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
