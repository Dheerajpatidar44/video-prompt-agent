"""Smoke test for WaveSpeed Wan 3.0 API."""
import asyncio
import sys
import argparse

from app.core.config import settings
from app.services.video_generation.wavespeed_client import WaveSpeedClient
from app.services.video_generation.cost import estimate_clip_cost_usd

async def main():
    parser = argparse.ArgumentParser(description="Run a real video generation smoke test.")
    parser.add_argument("--confirm", action="store_true", help="Confirm execution and spend money")
    args = parser.parse_args()

    resolution = settings.wavespeed_resolution
    duration = 2.0
    aspect = "9:16"
    cost = estimate_clip_cost_usd(duration, resolution)
    
    print(f"Estimated cost for this smoke test: ${cost:.2f} (2s @ {resolution})")
    
    if not args.confirm:
        print("Run with --confirm to actually execute and spend money.")
        sys.exit(1)

    print("Initializing WaveSpeedClient...")
    client = WaveSpeedClient(
        api_key=settings.wavespeed_api_key.get_secret_value(),
        base_url=settings.wavespeed_base_url,
        model_path=settings.wavespeed_model_path,
        resolution=resolution,
        generate_audio=settings.wavespeed_generate_audio,
        enable_prompt_expansion=settings.wavespeed_enable_prompt_expansion,
        negative_prompt_mode=settings.wavespeed_negative_prompt_mode,
        request_timeout=settings.wavespeed_request_timeout_seconds,
    )

    prompt = "a steaming coffee cup on a wooden table, soft morning light"
    print(f"Submitting job... Prompt: {prompt!r}")
    
    try:
        prediction_id = await client.submit_job(
            prompt_text=prompt,
            duration_seconds=duration,
            aspect_ratio=aspect
        )
        print(f"Job submitted successfully. Prediction ID: {prediction_id}")
        
        while True:
            await asyncio.sleep(5)
            print("Checking status...")
            status = await client.check_status(prediction_id)
            print(f"Status: {status['status']}")
            
            if status["status"] == "COMPLETED":
                print(f"Success! Video URL: {status['video_url']}")
                break
            elif status["status"] == "FAILED":
                print(f"Job failed: {status['error']}")
                sys.exit(1)
                
    except Exception as e:
        print(f"Error during smoke test: {e}")
        sys.exit(1)
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
