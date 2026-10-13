"""Manual smoke test CLI for Google Veo 3.1 Lite (Gemini API).

Runs an end-to-end smoke test against the live Veo API:
  submit_job -> poll check_status -> download_video -> save to file.

Cost: ~$0.20 for 4s at 720p.
Requires GEMINI_API_KEY to be set in .env.
"""
import argparse
import asyncio
import os
import sys
import tempfile
import time

# Ensure backend directory is in sys.path when run directly as a script
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings
from app.services.video_generation.cost import estimate_clip_cost_usd
from app.services.video_generation.veo_client import VeoClient


async def run_smoke_test(duration: float, aspect: str, output_path: str) -> None:
    api_key = settings.gemini_api_key.get_secret_value()
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set in .env. Please set it before running this test.")
        sys.exit(1)

    resolution = settings.veo_resolution
    client = VeoClient(
        api_key=api_key,
        base_url=settings.veo_base_url,
        model=settings.veo_model,
        resolution=resolution,
        person_generation=settings.veo_person_generation,
        negative_prompt_mode=settings.veo_negative_prompt_mode,
        request_timeout=settings.veo_request_timeout_seconds,
        download_timeout=settings.veo_download_timeout_seconds,
        max_prompt_tokens=settings.veo_max_prompt_tokens,
    )

    prompt = "a steaming coffee cup on a wooden table, soft morning light"
    print(f"\n[Veo Smoke Test]")
    print(f"Model: {settings.veo_model}")
    print(f"Resolution: {resolution}")
    print(f"Duration: {duration}s")
    print(f"Aspect ratio: {aspect}")
    print(f"Output path: {output_path}")
    print(f"Prompt: {prompt!r}")
    print("NOTE: Pressing Ctrl+C does NOT cancel the job at Google; it will still be billed.\n")

    start_time = time.time()
    try:
        print("Submitting generation job to Veo...")
        operation_name = await client.submit_job(
            prompt_text=prompt,
            duration_seconds=duration,
            aspect_ratio=aspect,
        )
        print(f"Job submitted successfully! Operation name: {operation_name}")

        max_wait = settings.video_job_max_wait_seconds
        video_url = None

        print("Polling status every 5 seconds...")
        while time.time() - start_time < max_wait:
            await asyncio.sleep(5)
            status_res = await client.check_status(operation_name)
            current_status = status_res.get("status")
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed}s] Status: {current_status}")

            if current_status == "COMPLETED":
                video_url = status_res.get("video_url")
                print(f"Operation completed! Result URI: {video_url}")
                break
            elif current_status == "FAILED":
                err = status_res.get("error", "Unknown error")
                print(f"ERROR: Generation job failed: {err}")
                sys.exit(1)

        if not video_url:
            print(f"ERROR: Job timed out after {max_wait}s without completing.")
            sys.exit(1)

        print("\nDownloading video (authenticated download)...")
        video_bytes = await client.download_video(video_url)
        print(f"Downloaded {len(video_bytes)} bytes successfully.")

        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(video_bytes)

        total_elapsed = int(time.time() - start_time)
        print(f"\n SUCCESS! Video saved to: {output_path}")
        print(f"File size: {len(video_bytes):,} bytes | Total elapsed time: {total_elapsed}s")

    except KeyboardInterrupt:
        print("\nSmoke test interrupted by user. (Google job may still complete and be billed).")
        sys.exit(130)
    except Exception as exc:
        print(f"\nERROR during smoke test: {exc}")
        sys.exit(1)
    finally:
        await client.aclose()


def main():
    parser = argparse.ArgumentParser(description="Manual smoke test for Google Veo 3.1 Lite")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually execute the API call and spend real money (~$0.20).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        choices=[4, 6, 8],
        default=4,
        help="Clip duration in seconds (4, 6, or 8; default 4).",
    )
    parser.add_argument(
        "--aspect",
        type=str,
        choices=["9:16", "16:9"],
        default="9:16",
        help="Aspect ratio (9:16 or 16:9; default 9:16).",
    )
    default_output = os.path.join(tempfile.gettempdir(), f"veo_smoke_test_{int(time.time())}.mp4")
    parser.add_argument(
        "--output",
        type=str,
        default=default_output,
        help=f"File path to save the generated MP4 (default: {default_output}).",
    )

    args = parser.parse_args()

    resolution = settings.veo_resolution
    cost = estimate_clip_cost_usd(args.duration, resolution)
    print(f"Estimated cost for this smoke test: ${cost:.2f} ({args.duration}s @ {resolution})")

    if not args.confirm:
        print("Dry run complete. Run with --confirm to actually execute and spend money (~$0.20).")
        sys.exit(0)

    asyncio.run(run_smoke_test(args.duration, args.aspect, args.output))


if __name__ == "__main__":
    main()
