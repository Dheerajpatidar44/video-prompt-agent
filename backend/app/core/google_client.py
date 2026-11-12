"""Unified Google GenAI Client Factory.

Reused across:
1. Gemini LLM Service (Script analysis & prompt generation) - defaults to location="global"
2. Google Veo Client (Video generation) - defaults to location="us-central1"
3. Gemini Image Service (Keyframe generation) - defaults to location="global"
"""
import os
import logging
from typing import Optional
from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_genai_client(location: Optional[str] = None) -> genai.Client:
    """Creates and returns a genai.Client configured for Vertex AI or Google AI Studio.

    Args:
        location: Specific Google Cloud region/location (e.g. "global", "us-central1").
                 If omitted, uses settings.google_cloud_location or "us-central1".
    """
    raw_key = settings.google_api_key.get_secret_value() if settings.google_api_key else ""

    if not raw_key and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        # If neither key nor ADC credentials exist, warn or raise
        logger.warning("GOOGLE_API_KEY is empty in settings and no GOOGLE_APPLICATION_CREDENTIALS found.")

    is_vertex = bool(
        settings.google_cloud_project
        or os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("true", "1")
        or (raw_key and raw_key.startswith("AQ."))
    )

    if is_vertex:
        target_location = location or settings.google_cloud_location or "us-central1"
        client_kwargs = {
            "vertexai": True,
            "location": target_location,
        }
        if raw_key:
            client_kwargs["api_key"] = raw_key
        if settings.google_cloud_project:
            client_kwargs["project"] = settings.google_cloud_project

        logger.debug(
            f"Creating Vertex AI genai.Client (project={settings.google_cloud_project}, location={target_location})"
        )
        return genai.Client(**client_kwargs)

    logger.debug("Creating Google AI Studio genai.Client (Developer API)")
    return genai.Client(
        api_key=raw_key,
        http_options=types.HttpOptions(api_version="v1"),
    )
