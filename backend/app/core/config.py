from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Literal

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

    # Cloudinary Config
    cloudinary_cloud_name: str = Field("default", validation_alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field("default", validation_alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field("default", validation_alias="CLOUDINARY_API_SECRET")

    # Video Generation Config
    use_mock_video_api: bool = Field(True, validation_alias="USE_MOCK_VIDEO_API")
    video_generation_concurrency_limit: int = Field(3, validation_alias="VIDEO_GENERATION_CONCURRENCY_LIMIT")
    video_poll_interval_seconds: int = Field(10, validation_alias="VIDEO_POLL_INTERVAL_SECONDS")
    video_max_retries: int = Field(2, validation_alias="VIDEO_MAX_RETRIES")

    # WaveSpeed Config
    video_provider: str = Field("wavespeed", validation_alias="VIDEO_PROVIDER")
    wavespeed_api_key: SecretStr = Field(SecretStr(""), validation_alias="WAVESPEED_API_KEY")
    wavespeed_base_url: str = Field("https://api.wavespeed.ai/api/v3", validation_alias="WAVESPEED_BASE_URL")
    wavespeed_model_path: str = Field("alibaba/wan-3.0/text-to-video", validation_alias="WAVESPEED_MODEL_PATH")
    wavespeed_resolution: Literal["480p", "720p", "1080p"] = Field("480p", validation_alias="WAVESPEED_RESOLUTION")
    wavespeed_generate_audio: bool = Field(True, validation_alias="WAVESPEED_GENERATE_AUDIO")
    wavespeed_enable_prompt_expansion: bool = Field(False, validation_alias="WAVESPEED_ENABLE_PROMPT_EXPANSION")
    wavespeed_negative_prompt_mode: Literal["drop", "append"] = Field("drop", validation_alias="WAVESPEED_NEGATIVE_PROMPT_MODE")
    wavespeed_request_timeout_seconds: float = Field(30.0, validation_alias="WAVESPEED_REQUEST_TIMEOUT_SECONDS")

    # Cost / safety guards (apply to real providers only, never to the mock)
    video_job_max_wait_seconds: int = Field(900, validation_alias="VIDEO_JOB_MAX_WAIT_SECONDS")
    video_status_max_consecutive_errors: int = Field(20, validation_alias="VIDEO_STATUS_MAX_CONSECUTIVE_ERRORS")
    video_max_shots_per_project: int = Field(10, validation_alias="VIDEO_MAX_SHOTS_PER_PROJECT")
    video_max_total_seconds_per_project: int = Field(40, validation_alias="VIDEO_MAX_TOTAL_SECONDS_PER_PROJECT")
    video_max_estimated_cost_usd: float = Field(2.0, validation_alias="VIDEO_MAX_ESTIMATED_COST_USD")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
