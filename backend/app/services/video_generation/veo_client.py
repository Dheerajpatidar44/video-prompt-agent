"""Google Veo 3.1 Lite client for video generation via the Gemini API.

Uses plain REST through httpx — no Google SDK dependency.

Submit:  POST {base}/models/{model}:predictLongRunning
Poll:    GET  {base}/{operation_name}
Download: GET <video uri> with the API key header (authenticated download)
"""
import asyncio
import logging
import math
import random
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.services.video_generation.base_client import (
    VideoGenerationClient,
    PermanentVideoError,
    TransientVideoError,
)
from app.services.video_generation.cost import billed_seconds, estimate_clip_cost_usd

logger = logging.getLogger(__name__)

AUTH_HEADER = "x-goog-api-key"

# Whether durationSeconds is sent as int (True) or string (False).
# Open question — default to integer based on REST samples.
DURATION_AS_INT = True

# Safety cap for video download size.
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

# Max redirects when downloading authenticated video.
MAX_DOWNLOAD_REDIRECTS = 5

# Regex for validating external_job_id (operation names like "models/veo-3.1.../operations/abc123")
_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-.]+)*$")


class VeoClient(VideoGenerationClient):
    """Gemini API client for Veo 3.1 Lite text-to-video generation."""

    requires_authenticated_download: bool = True

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        resolution: str,
        person_generation: str,
        negative_prompt_mode: str,
        request_timeout: float,
        download_timeout: float,
        max_prompt_tokens: int,
        client: Optional[httpx.AsyncClient] = None,
    ):
        if not api_key:
            raise PermanentVideoError(
                "GEMINI_API_KEY is not set. Add it to .env or set USE_MOCK_VIDEO_API=true."
            )

        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.resolution = resolution
        self.person_generation = person_generation
        self.negative_prompt_mode = negative_prompt_mode
        self.request_timeout = request_timeout
        self.download_timeout = download_timeout
        self.max_prompt_tokens = max_prompt_tokens

        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.request_timeout, connect=5.0),
                headers={AUTH_HEADER: self._api_key},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #
    # Internal HTTP helper with retry logic                                #
    # ------------------------------------------------------------------ #

    async def _request(
        self,
        method: str,
        url: str,
        json_data: dict | None = None,
    ) -> dict:
        """Make an HTTP request with retry/error handling.

        POST (not idempotent): retry only on ConnectError, ConnectTimeout and 429.
        GET  (idempotent): additionally retry on ReadTimeout, 5xx and network errors.
        """
        client = await self._get_client()
        max_attempts = 4  # initial + 3 retries

        for attempt in range(max_attempts):
            try:
                response = await client.request(
                    method,
                    url,
                    json=json_data,
                    headers={AUTH_HEADER: self._api_key},
                )

                # --- 401 / 403: authentication failure, never retry ---
                if response.status_code in (401, 403):
                    raise PermanentVideoError(
                        "Authentication failed — check GEMINI_API_KEY, that billing/paid tier "
                        "is enabled for Veo, and that the model is available in your region."
                    )

                # --- 429: rate limited / quota exhausted ---
                if response.status_code == 429:
                    try:
                        err_body = response.json()
                        err_obj = err_body.get("error", {})
                        error_text = err_obj.get("message") or err_obj.get("status") or response.text
                    except Exception:
                        error_text = response.text
                    if attempt == max_attempts - 1:
                        raise TransientVideoError(
                            f"Rate limited / Quota exhausted (429): {str(error_text)[:300]}"
                        )
                    retry_after = float(response.headers.get("Retry-After", 2 ** attempt))
                    jitter = random.uniform(0, 0.5)
                    await asyncio.sleep(retry_after + jitter)
                    continue

                # --- Other 4xx: permanent, no retry ---
                if 400 <= response.status_code < 500:
                    try:
                        err_body = response.json()
                        err_obj = err_body.get("error", {})
                        error_text = err_obj.get("message") or err_obj.get("status") or response.text
                    except Exception:
                        error_text = response.text
                    raise PermanentVideoError(
                        f"Provider rejected request ({response.status_code}): {str(error_text)[:200]}"
                    )

                # --- 5xx: server error ---
                if response.status_code >= 500:
                    if method == "GET" and attempt < max_attempts - 1:
                        await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                        continue
                    # POST 5xx: ambiguous — job may exist. DO NOT retry.
                    raise TransientVideoError(
                        f"Provider server error ({response.status_code}): {response.text[:200]}"
                    )

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
                # POST read-timeout: ambiguous — DO NOT retry
                if method != "GET":
                    raise TransientVideoError(f"Timeout error: {e}") from e
                if attempt < max_attempts - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                    continue
                raise TransientVideoError(f"Timeout error: {e}") from e

            except httpx.RequestError as e:
                if method == "GET" and attempt < max_attempts - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.5))
                    continue
                raise TransientVideoError(f"Request error: {e}") from e

        raise TransientVideoError("Max retries exceeded")

    # ------------------------------------------------------------------ #
    # submit_job                                                           #
    # ------------------------------------------------------------------ #

    async def submit_job(
        self,
        prompt_text: str,
        duration_seconds: float,
        aspect_ratio: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
    ) -> str:
        # --- Duration ---
        duration = billed_seconds(duration_seconds, self.resolution)
        if duration != round(duration_seconds):
            logger.info(f"planned {duration_seconds}s → Veo generates {duration}s")
        if round(float(duration_seconds), 3) > 8:
            logger.warning(
                f"shot is longer than Veo's 8 s maximum; it will be {duration} s"
            )

        # --- Aspect ratio ---
        aspect = self._normalize_aspect_ratio(aspect_ratio)

        # --- Negative prompt handling ---
        if negative_prompt:
            if self.negative_prompt_mode == "append":
                append_text = f"\n\nAvoid: {negative_prompt}"
                if len(append_text) > 300:
                    append_text = append_text[:297] + "..."
                candidate = prompt_text + append_text
                estimated_tokens = math.ceil(len(candidate) / 4)
                if estimated_tokens <= self.max_prompt_tokens:
                    prompt_text = candidate
                else:
                    logger.debug(
                        "negative_prompt would exceed token guard after append, dropping it"
                    )
            else:
                logger.debug("negative_prompt mode is 'drop', ignoring negative_prompt")

        if reference_image_url:
            logger.debug(
                "reference_image_url is not supported on Veo 3.1 Lite, ignoring"
            )

        # --- Token guard ---
        estimated_tokens = math.ceil(len(prompt_text) / 4)
        if estimated_tokens > self.max_prompt_tokens:
            raise PermanentVideoError(
                f"Prompt is about {estimated_tokens} tokens; Veo accepts at most 1,024. "
                f"Shorten the prompt."
            )

        # --- Build body ---
        parameters: dict = {
            "aspectRatio": aspect,
            "durationSeconds": duration if DURATION_AS_INT else str(duration),
            "resolution": self.resolution,
        }
        if self.person_generation:
            parameters["personGeneration"] = self.person_generation

        body = {
            "instances": [{"prompt": prompt_text}],
            "parameters": parameters,
        }

        url = f"{self.base_url}/models/{self.model}:predictLongRunning"
        logger.debug(f"Submitting Veo job to {url}")

        response_data = await self._request("POST", url, json_data=body)

        operation_name = response_data.get("name")
        if not operation_name:
            raise PermanentVideoError(
                f"Missing 'name' in response: {str(response_data)[:200]}"
            )

        cost = estimate_clip_cost_usd(duration_seconds, self.resolution)
        logger.info(
            f"Submitted Veo job {operation_name}: {duration}s at {self.resolution} "
            f"(est. cost ${cost:.2f})"
        )

        return operation_name

    # ------------------------------------------------------------------ #
    # check_status                                                         #
    # ------------------------------------------------------------------ #

    async def check_status(self, external_job_id: str) -> dict:
        # Validate external_job_id to prevent URL injection
        if not external_job_id or external_job_id.startswith("/"):
            raise PermanentVideoError(
                f"Invalid operation id: must not be empty or start with '/'"
            )
        if ".." in external_job_id:
            raise PermanentVideoError(
                f"Invalid operation id: must not contain '..'"
            )
        if not _OPERATION_ID_RE.match(external_job_id):
            raise PermanentVideoError(
                f"Invalid operation id: contains disallowed characters"
            )

        url = f"{self.base_url}/{external_job_id}"
        try:
            response_data = await self._request("GET", url)
        except PermanentVideoError as e:
            if "404" in str(e):
                raise PermanentVideoError(
                    f"Unknown operation: {external_job_id}"
                ) from e
            raise

        done = response_data.get("done", False)

        if not done:
            return {"status": "PROCESSING", "video_url": None, "error": None}

        # --- done is True ---

        # Check for error
        error_obj = response_data.get("error")
        if error_obj and isinstance(error_obj, dict):
            code = error_obj.get("code", "")
            status = error_obj.get("status", "")
            message = error_obj.get("message", "")
            return {
                "status": "FAILED",
                "video_url": None,
                "error": f"{code} {status}: {message}"[:200],
            }

        # Check for generated video
        response_inner = response_data.get("response", {})
        gvr = response_inner.get("generateVideoResponse", response_inner)
        samples = gvr.get("generatedSamples", [])

        if samples and isinstance(samples, list):
            for sample in samples:
                video = sample.get("video", {}) if isinstance(sample, dict) else {}
                uri = video.get("uri") if isinstance(video, dict) else None
                if uri:
                    return {"status": "COMPLETED", "video_url": uri, "error": None}

        # Done but no video — likely safety filter
        filtered_reasons = gvr.get("raiMediaFilteredReasons", [])
        filtered_count = gvr.get("raiMediaFilteredCount", 0)

        if filtered_reasons or filtered_count:
            reasons_str = ", ".join(str(r) for r in filtered_reasons) if filtered_reasons else "unknown"
            return {
                "status": "FAILED",
                "video_url": None,
                "error": f"Video was blocked by Google's safety filters: {reasons_str}",
                "retryable": False,
            }

        return {
            "status": "FAILED",
            "video_url": None,
            "error": "Operation finished without a video",
            "retryable": False,
        }

    # ------------------------------------------------------------------ #
    # download_video (authenticated, redirect-safe)                        #
    # ------------------------------------------------------------------ #

    async def download_video(self, video_url: str) -> bytes:
        """Download video from a Veo result URI with authenticated redirects.

        The API key header is only attached on hops whose host ends with
        .googleapis.com; it is stripped for any other host (e.g. a signed
        storage URL after redirect).
        """
        parsed = urlparse(video_url)
        if parsed.scheme != "https":
            raise PermanentVideoError(
                f"Refusing non-https video URL: {parsed.scheme}"
            )
        if not parsed.hostname or not parsed.hostname.endswith(".googleapis.com"):
            raise PermanentVideoError(
                "Refusing to send API key to non-Google host: "
                f"{parsed.hostname}"
            )

        current_url = video_url
        client = await self._get_client()

        for hop in range(MAX_DOWNLOAD_REDIRECTS + 1):
            hop_parsed = urlparse(current_url)
            if hop_parsed.scheme != "https":
                raise PermanentVideoError(
                    f"Redirect to non-https URL at hop {hop}: {hop_parsed.scheme}"
                )

            # Only attach API key on Google hosts
            headers = {}
            if hop_parsed.hostname and hop_parsed.hostname.endswith(".googleapis.com"):
                headers[AUTH_HEADER] = self._api_key

            try:
                response = await client.send(
                    client.build_request("GET", current_url, headers=headers),
                    follow_redirects=False,
                    stream=False,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                raise TransientVideoError(f"Download connection error: {e}") from e
            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                raise TransientVideoError(f"Download timeout: {e}") from e
            except httpx.RequestError as e:
                raise TransientVideoError(f"Download request error: {e}") from e

            # Handle redirects manually
            if response.status_code in (301, 302, 303, 307, 308):
                if hop >= MAX_DOWNLOAD_REDIRECTS:
                    raise PermanentVideoError(
                        f"Too many redirects ({MAX_DOWNLOAD_REDIRECTS}) downloading video"
                    )
                location = response.headers.get("Location", "")
                if not location:
                    raise PermanentVideoError("Redirect without Location header")
                current_url = urljoin(current_url, location)
                continue

            # Error responses
            if response.status_code in (401, 403, 404):
                raise PermanentVideoError(
                    f"Download failed ({response.status_code}): "
                    f"{response.text[:200] if response.text else 'no body'}"
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise TransientVideoError(
                    f"Download server error ({response.status_code}): "
                    f"{response.text[:200] if response.text else 'no body'}"
                )
            if response.status_code != 200:
                raise PermanentVideoError(
                    f"Unexpected download status ({response.status_code})"
                )

            # Check content type — reject JSON/HTML/text
            content_type = response.headers.get("content-type", "")
            if any(t in content_type.lower() for t in ("json", "html", "text/")):
                raise PermanentVideoError(
                    f"Expected video content-type, got {content_type}: "
                    f"{response.text[:200] if response.text else 'no body'}"
                )

            data = response.content
            if not data:
                raise PermanentVideoError("Download returned empty body")
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise PermanentVideoError(
                    f"Download exceeds {MAX_DOWNLOAD_BYTES} byte limit"
                )

            logger.info(
                f"Downloaded {len(data)} bytes from {hop_parsed.hostname}"
            )
            return data

        raise PermanentVideoError("Download redirect loop exhausted")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_aspect_ratio(aspect_ratio: str) -> str:
        """Map an arbitrary aspect ratio string to one Veo supports: 16:9 or 9:16."""
        if aspect_ratio in ("16:9", "9:16"):
            return aspect_ratio

        # Try to parse w:h
        try:
            parts = aspect_ratio.split(":")
            w, h = float(parts[0]), float(parts[1])
            result = "16:9" if w >= h else "9:16"
        except (ValueError, IndexError):
            result = "16:9"

        logger.warning(
            f"Aspect ratio {aspect_ratio!r} not supported by Veo, mapping to {result!r}"
        )
        return result
