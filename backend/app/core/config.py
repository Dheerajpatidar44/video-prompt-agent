import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Literal

_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"

class Settings(BaseSettings):
    app_name: str = Field("Video Prompt Agent", validation_alias="APP_NAME")
    app_env: str = Field("development", validation_alias="APP_ENV")
    app_host: str = Field("127.0.0.1", validation_alias="APP_HOST")
    app_port: int = Field(8000, validation_alias="APP_PORT")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL") 

    # LLM Provider Selection (gemini | claude)
    llm_provider: Literal["gemini", "claude"] = Field("gemini", validation_alias="LLM_PROVIDER")

    # Gemini LLM Config
    gemini_llm_model: str = Field("gemini-2.5-flash", validation_alias="GEMINI_LLM_MODEL")
    gemini_llm_location: str = Field("global", validation_alias="GEMINI_LLM_LOCATION")
    gemini_llm_max_output_tokens: int = Field(20000, validation_alias="GEMINI_LLM_MAX_OUTPUT_TOKENS")
    gemini_llm_temperature: float = Field(0.3, validation_alias="GEMINI_LLM_TEMPERATURE")
    gemini_llm_concurrency: int = Field(3, validation_alias="GEMINI_LLM_CONCURRENCY")
    gemini_llm_validation_retries: int = Field(2, validation_alias="GEMINI_LLM_VALIDATION_RETRIES")

    # Anthropic Claude Config (Optional when Gemini is selected)
    anthropic_api_key: str = Field("", validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-5", validation_alias="ANTHROPIC_MODEL")
    anthropic_max_tokens: int = Field(20000, validation_alias="ANTHROPIC_MAX_TOKENS")
    anthropic_temperature: float = Field(0.3, validation_alias="ANTHROPIC_TEMPERATURE")
    anthropic_max_concurrency: int = Field(3, validation_alias="ANTHROPIC_MAX_CONCURRENCY") 
    
    # System Defaults for safe fields
    default_duration_seconds: int = Field(10, validation_alias="DEFAULT_DURATION_SECONDS")
    default_aspect_ratio: str = Field("16:9", validation_alias="DEFAULT_ASPECT_RATIO")

    # Cloudinary Config
    cloudinary_cloud_name: str = Field("default", validation_alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field("default", validation_alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field("default", validation_alias="CLOUDINARY_API_SECRET")

    # Image Generation Config
    use_mock_image_api: bool = Field(True, validation_alias="USE_MOCK_IMAGE_API")

    # Video Generation Config
    use_mock_video_api: bool = Field(True, validation_alias="USE_MOCK_VIDEO_API")
    video_generation_concurrency_limit: int = Field(3, validation_alias="VIDEO_GENERATION_CONCURRENCY_LIMIT")
    video_poll_interval_seconds: int = Field(10, validation_alias="VIDEO_POLL_INTERVAL_SECONDS")
    video_max_retries: int = Field(2, validation_alias="VIDEO_MAX_RETRIES")
    video_submit_min_interval_seconds: float = Field(2.5, validation_alias="VIDEO_SUBMIT_MIN_INTERVAL_SECONDS", ge=0.0)
    video_submit_max_retries: int = Field(4, validation_alias="VIDEO_SUBMIT_MAX_RETRIES", ge=0)
    video_submit_backoff_base_seconds: float = Field(15.0, validation_alias="VIDEO_SUBMIT_BACKOFF_BASE_SECONDS", ge=0.0)
    video_submit_backoff_max_seconds: float = Field(60.0, validation_alias="VIDEO_SUBMIT_BACKOFF_MAX_SECONDS", ge=0.0)

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

    # Gemini Image Generation Config
    gemini_image_model: str = Field("gemini-3.1-flash-image", validation_alias="GEMINI_IMAGE_MODEL")
    gemini_image_concurrency_limit: int = Field(1, validation_alias="GEMINI_IMAGE_CONCURRENCY_LIMIT")
    gemini_image_min_interval_seconds: float = Field(2.0, validation_alias="GEMINI_IMAGE_MIN_INTERVAL_SECONDS")
    image_output_dir: str = Field("static/generated_images", validation_alias="IMAGE_OUTPUT_DIR")
    gemini_image_size: str = Field("1K", validation_alias="GEMINI_IMAGE_SIZE")

    # Cost / safety guards (apply to real providers only, never to the mock)
    video_job_max_wait_seconds: int = Field(900, validation_alias="VIDEO_JOB_MAX_WAIT_SECONDS")
    video_status_max_consecutive_errors: int = Field(20, validation_alias="VIDEO_STATUS_MAX_CONSECUTIVE_ERRORS")
    video_max_shots_per_project: int = Field(10, validation_alias="VIDEO_MAX_SHOTS_PER_PROJECT")
    video_max_total_seconds_per_project: int = Field(40, validation_alias="VIDEO_MAX_TOTAL_SECONDS_PER_PROJECT")
    video_max_estimated_cost_usd: float = Field(5.0, validation_alias="VIDEO_MAX_ESTIMATED_COST_USD")

    # Image-regeneration retry on Veo safety/policy rejection (e.g. error 15236754):
    # Maximum number of times to regenerate a fresh image and re-submit to Veo per job.
    video_image_regen_max_retries: int = Field(1, validation_alias="VIDEO_IMAGE_REGEN_MAX_RETRIES")

    model_config = SettingsConfigDict(env_file=[str(_backend_env), ".env"], env_file_encoding="utf-8", extra="ignore")

settings = Settings()
