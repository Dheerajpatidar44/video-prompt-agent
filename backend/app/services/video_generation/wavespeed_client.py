"""WaveSpeed Wan 3.0 client for video generation."""
import asyncio
import logging
import random
from typing import Optional

import httpx

from app.services.video_generation.base_client import (
    VideoGenerationClient,
    PermanentVideoError,
    TransientVideoError,
)
from app.services.video_generation.cost import billed_seconds, estimate_clip_cost_usd

logger = logging.getLogger(__name__)

AUDIO_PARAM = "generate_audio"


class WaveSpeedClient(VideoGenerationClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_path: str,
        resolution: str,
        generate_audio: bool,
        enable_prompt_expansion: bool,
        negative_prompt_mode: str,
        request_timeout: float,
        client: Optional[httpx.AsyncClient] = None,
    ):
        if not api_key:
            raise PermanentVideoError("WAVESPEED_API_KEY is not set. Add it to .env or set USE_MOCK_VIDEO_API=true.")
            
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_path = model_path
        self.resolution = resolution
        self.generate_audio = generate_audio
        self.enable_prompt_expansion = enable_prompt_expansion
        self.negative_prompt_mode = negative_prompt_mode
        self.request_timeout = request_timeout
        
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.request_timeout, connect=5.0),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, url: str, json_data: dict | None = None) -> dict:
        client = await self._get_client()
        max_attempts = 4 # initial + 3 retries
        
        for attempt in range(max_attempts):
            try:
                response = await client.request(method, url, json=json_data)
                
                if response.status_code in (401, 403):
                    raise PermanentVideoError("Authentication failed — check WAVESPEED_API_KEY")
                    
                if response.status_code == 429:
                    if attempt == max_attempts - 1:
                        raise TransientVideoError(f"Rate limited after {max_attempts} attempts")
                    retry_after = float(response.headers.get("Retry-After", 2 ** attempt))
                    jitter = random.uniform(0, 0.5)
                    await asyncio.sleep(retry_after + jitter)
                    continue

                if 400 <= response.status_code < 500:
                    # Other 4xx errors
                    try:
                        error_text = response.json().get("message") or response.json().get("error") or response.text
                    except Exception:
                        error_text = response.text
                    raise PermanentVideoError(f"Provider rejected request ({response.status_code}): {error_text[:200]}")
                    
                if response.status_code >= 500:
                    if method == "GET" and attempt < max_attempts - 1:
                        await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                        continue
                    raise TransientVideoError(f"Provider server error ({response.status_code}): {response.text[:200]}")
                    
                response.raise_for_status()
                
                try:
                    return response.json()
                except ValueError as e:
                    if method == "GET":
                        raise TransientVideoError("Malformed JSON in response") from e
                    else:
                        raise PermanentVideoError("Malformed JSON in response") from e

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                    continue
                raise TransientVideoError(f"Connection error: {e}") from e
                
            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                if method == "GET" and attempt < max_attempts - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                    continue
                raise TransientVideoError(f"Timeout error: {e}") from e
                
            except httpx.RequestError as e:
                 if method == "GET" and attempt < max_attempts - 1:
                     await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                     continue
                 raise TransientVideoError(f"Request error: {e}") from e
                 
        raise TransientVideoError("Max retries exceeded")

    async def submit_job(
        self,
        prompt_text: str,
        duration_seconds: float,
        aspect_ratio: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
    ) -> str:
        billed_sec = billed_seconds(duration_seconds)
        if billed_sec != round(duration_seconds):
            logger.info(f"requested {duration_seconds}s, provider minimum {billed_sec}s")
            
        supported_aspect_ratios = {"16:9", "9:16", "1:1", "4:3", "3:4"}
        if aspect_ratio not in supported_aspect_ratios:
            logger.warning(f"Aspect ratio {aspect_ratio} not supported, falling back to 16:9")
            aspect_ratio = "16:9"

        if negative_prompt:
            if self.negative_prompt_mode == "append":
                append_text = f"\n\nAvoid: {negative_prompt}"
                # Trim at sentence boundary if possible, but keep it short (~300 chars for the append portion)
                if len(append_text) > 300:
                    append_text = append_text[:297] + "..."
                prompt_text += append_text
            else:
                logger.debug("negative_prompt mode is 'drop', ignoring negative_prompt")
                
        if reference_image_url:
            logger.debug("reference_image_url is not supported on this endpoint, ignoring")

        payload = {
            "prompt": prompt_text,
            "resolution": self.resolution,
            "aspect_ratio": aspect_ratio,
            "duration": billed_sec,
            "enable_prompt_expansion": self.enable_prompt_expansion,
            AUDIO_PARAM: self.generate_audio,
        }

        url = f"{self.base_url}/{self.model_path}"
        logger.debug(f"Submitting job to {url}")
        
        response_data = await self._request("POST", url, json_data=payload)
        
        data = response_data.get("data") if isinstance(response_data.get("data"), dict) else response_data
        prediction_id = data.get("id")
        
        if not prediction_id:
            raise PermanentVideoError(f"Missing id in response: {str(response_data)[:200]}")
            
        cost = estimate_clip_cost_usd(duration_seconds, self.resolution)
        logger.info(f"Submitted WaveSpeed job {prediction_id}: {billed_sec}s at {self.resolution} (est. cost ${cost:.2f})")
        
        return prediction_id

    async def check_status(self, external_job_id: str) -> dict:
        url = f"{self.base_url}/predictions/{external_job_id}/result"
        try:
            response_data = await self._request("GET", url)
        except PermanentVideoError as e:
            if "404" in str(e):
                raise PermanentVideoError(f"Unknown job id: {external_job_id}") from e
            raise

        data = response_data.get("data") if isinstance(response_data.get("data"), dict) else response_data
        status_raw = str(data.get("status", "")).lower()
        
        if status_raw == "completed":
            outputs = data.get("outputs", [])
            video_url = outputs[0] if outputs and isinstance(outputs, list) and isinstance(outputs[0], str) else None
            return {"status": "COMPLETED", "video_url": video_url, "error": None}
            
        if status_raw in ("failed", "cancelled", "timeout", "deleted"):
            return {"status": "FAILED", "video_url": None, "error": data.get("error") or status_raw}
            
        return {"status": "PROCESSING", "video_url": None, "error": None}
