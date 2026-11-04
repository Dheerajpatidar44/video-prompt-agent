"""CLI tool to test Real Image Generation using Gemini 3.1 Flash Image.

Usage:
    cd backend
    .\\venv\\Scripts\\python test_real_image_gen.py
    .\\venv\\Scripts\\python test_real_image_gen.py "A glowing futuristic smartwatch on a marble table"
"""
import asyncio
import os
import sys
from pathlib import Path
from PIL import Image

# Ensure app can be imported
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# Fix Windows console encoding for special characters
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.core.config import settings
from app.services.image_generation.gemini_image_service import (
    get_gemini_image_service,
    ImageGenerationError,
)


async def main():
    print("=" * 70)
    print("       REAL GEMINI IMAGE GENERATION TEST (gemini-3.1-flash-image)")
    print("=" * 70)

    # 1. Verify GOOGLE_API_KEY
    api_key = settings.google_api_key.get_secret_value() if settings.google_api_key else ""
    if not api_key:
        print("\n[ERROR] GOOGLE_API_KEY backend/.env me set nahi hai!")
        print("Kripya backend/.env me GOOGLE_API_KEY=\"your_key\" add karein.")
        return

    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[*] Model ID         : {settings.gemini_image_model}")
    print(f"[*] API Key Detected : {masked_key} (Valid length: {len(api_key)})")
    print(f"[*] Output Directory : {settings.image_output_dir}")

    # 2. Test Prompt
    custom_prompt = sys.argv[1] if len(sys.argv) > 1 else None
    prompt = custom_prompt or (
        "Cinematic photorealistic portrait of a young Indian woman smiling warmly "
        "inside a modern sunlit minimalist coffee shop. "
        "Natural soft rim lighting, highly detailed skin texture, shallow depth of field, "
        "professional commercial cinematography, 16:9 aspect ratio."
    )

    print(f"\n[*] Generating real image for prompt:")
    print(f"    \"{prompt}\"")
    print("\nCalling Gemini API... (Kripya thoda wait karein...)")

    service = get_gemini_image_service()

    try:
        image_path = await service.generate_image(
            prompt=prompt,
            aspect_ratio="16:9",
        )

        if not image_path or not os.path.exists(image_path):
            print("\n[FAILED] API call hui lekin koi image file save nahi ho paayi.")
            return

        file_size_bytes = os.path.getsize(image_path)
        file_size_kb = file_size_bytes / 1024

        with Image.open(image_path) as img:
            width, height = img.size
            format_name = img.format

        print("\n" + "=" * 70)
        print("                  IMAGE GENERATION SUCCESS!")
        print("=" * 70)
        print(f"[+] Saved File Path : {image_path}")
        print(f"[+] Absolute Path   : {os.path.abspath(image_path)}")
        print(f"[+] Dimensions      : {width} x {height} px")
        print(f"[+] Format          : {format_name}")
        print(f"[+] File Size       : {file_size_kb:.2f} KB")
        print("=" * 70)
        print("\n[SUCCESS] Aapka real Gemini Image API 100% kaam kar raha hai!")
        print(f"Aap is image ko is path se open karke dekh sakte hain:")
        print(f"  {os.path.abspath(image_path)}\n")

    except ImageGenerationError as ige:
        print(f"\n[CONFIGURATION ERROR] {ige}")
    except Exception as exc:
        print(f"\n[API ERROR] Image generation fail ho gayi: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

