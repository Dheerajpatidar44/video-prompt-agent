"""CLI tool to test Python Image Pre-Analysis on any user-provided image.
Zero API keys or cloud services required.

Usage:
    venv\\Scripts\\python test_image_cli.py "C:\\path\\to\\your_image.jpg"
    venv\\Scripts\\python test_image_cli.py your_image.png
"""
import os
import sys
from pathlib import Path

# Fix Windows console encoding for special characters
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.services.image_analysis_service import ImageAnalysisService


def main():
    print("=" * 65)
    print("      IMAGE ANALYSIS TESTER (ZERO API KEY REQUIRED)")
    print("=" * 65)

    if len(sys.argv) < 2:
        print("\n[!] Bhai aapne koi image provide nahi ki hai.")
        print("\nKese chalana he:")
        print('  1. Agar image backend folder me he:')
        print('     venv\\Scripts\\python test_image_cli.py "my_photo.jpg"')
        print('\n  2. Agar image Desktop ya kisi aur folder me he:')
        print('     venv\\Scripts\\python test_image_cli.py "C:\\Users\\HP\\Desktop\\my_photo.jpg"')
        print("\n" + "=" * 65)
        return

    img_path = sys.argv[1].strip("\"'")

    if not os.path.exists(img_path):
        print(f"\n[ERROR] Di gayi file nahi mili: '{img_path}'")
        print("Kripya sahi path check karein.")
        return

    print(f"\nAnalyzing user image: {img_path} ...")

    with open(img_path, "rb") as f:
        img_bytes = f.read()

    filename = Path(img_path).name
    category_arg = sys.argv[2].strip().lower() if len(sys.argv) > 2 else "auto"
    profile = ImageAnalysisService.analyze_image_bytes(
        image_bytes=img_bytes,
        filename=filename,
        category=category_arg
    )

    print("\n" + "=" * 65)
    print("             EXTRACTION REPORT (LOCAL PYTHON)")
    print("=" * 65)
    print(f"[*] File Name      : {profile.filename}")
    print(f"[*] Category       : {profile.category.upper()} ({'Auto-Detected' if category_arg == 'auto' else 'User-Specified'})")
    print(f"[*] Dimensions     : {profile.width} x {profile.height} px")
    print(f"[*] Aspect Ratio   : {profile.aspect_ratio} ({'Vertical/Portrait' if profile.is_vertical else 'Horizontal/Landscape'})")
    print(f"[*] Dominant Color : {profile.dominant_color_hex}")
    print(f"[*] Color Palette  : {', '.join(profile.color_palette_hex)}")
    print(f"[*] Lighting       : {profile.lighting_style}")
    print(f"[*] Framing Type   : {profile.framing_type} (Detected Faces: {profile.detected_faces_count})")
    print(f"[*] Blur/Sharpness : Score = {profile.blur_score:.1f} ({'Sharp/Clear' if profile.is_sharp else 'Slightly Soft/Blurry'})")
    print(f"[*] Perceptual Hash: {profile.phash}")
    labels_str = ", ".join(profile.detected_labels) if profile.detected_labels else "(No text/labels detected)"
    print(f"[*] Detected Text  : {labels_str}")
    print("=" * 65)

    print("\n[+] LLM Prompt me bheja jaane waala Final Fact Summary:")
    print("-" * 65)
    print(profile.visual_summary_bullet)
    print("-" * 65)
    print("\n[SUCCESS] Image successfully analyze ho gayi bina kisi API key ke!\n")


if __name__ == "__main__":
    main()
