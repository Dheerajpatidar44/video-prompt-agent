r"""Real End-to-End Test for Prompt Generation using Gemini LLM.

This script makes a real API call to Gemini using our project's architecture
(app.llm.llm_service and GenerationResult) to generate cinematic video prompts.

Usage:
    cd backend
    .\venv\Scripts\python.exe scripts/test_real_prompt_generation.py
"""
import os
import sys
import json
import time
import asyncio
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Ensure TESTING is not set so real provider runs
os.environ.pop("TESTING", None)

from app.core.config import settings
from app.llm import get_llm_service, reset_llm_service
from app.schemas.generation import GenerationResult
from app.prompts.generation import GENERATION_PROMPT
from app.prompts.tool_rules import get_tool_rules
from app.services.video_generation.cost import estimate_llm_cost_usd


# ----------------------------------------------------------------------
# 1. Sample Video Specification for Prompt Generation
# ----------------------------------------------------------------------
SAMPLE_VIDEO_SPEC = {
    "title": "Luxury Apartment Evening Routine",
    "theme": "Cinematic realism, high-end lifestyle, serene luxury",
    "output_requirements": {
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        "target_tool": "Veo"
    },
    "characters": [
        {
            "id": "char_sophia",
            "name": "Sophia",
            "description": "Young elegant woman in her late 20s, wearing minimalist smart casual attire, gentle graceful posture.",
            "source": "SCRIPT"
        }
    ],
    "locations": [
        {
            "id": "loc_penthouse_foyer",
            "name": "Luxury Penthouse Foyer",
            "description": "Warm polished travertine marble floors, soft recessed warm ambient lighting, modern minimalist wooden credenza near front door.",
            "source": "SCRIPT"
        }
    ],
    "products": [
        {
            "id": "prod_designer_shoes",
            "name": "Designer Italian Leather Loafers",
            "description": "Handcrafted minimalist camel-tan Italian leather loafers with subtle gold buckle accent.",
            "source": "SCRIPT"
        }
    ],
    "continuity_bible": {
        "visual_style": "35mm anamorphic aesthetic, shallow depth of field, warm golden-hour dusk light streaming from floor-to-ceiling windows, subtle volumetric dust particles.",
        "pacing": "Slow, deliberate, peaceful",
        "color_palette": "Warm earth tones, cream travertine, amber accents, soft dusk shadows"
    },
    "actions": [
        {
            "id": "act_1",
            "character_id": "char_sophia",
            "description": "Sophia steps through the doorway into the foyer, gracefully slips off her designer leather shoes and neatly places them beside the entryway credenza."
        },
        {
            "id": "act_2",
            "character_id": "char_sophia",
            "description": "Close-up macro perspective of the leather shoes resting on polished marble with soft warm specular highlights on the gold buckle detail."
        }
    ]
}


async def run_prompt_generation_test():
    print("=" * 70)
    print("🎥 VIDEO PROMPT AGENT — REAL GEMINI PROMPT GENERATION TEST")
    print("=" * 70)

    # 1. Verify Configuration
    print(f"[*] Configured LLM Provider : {settings.llm_provider}")
    print(f"[*] Target Gemini Model     : {settings.gemini_llm_model}")
    print(f"[*] Google Cloud Location   : {settings.gemini_llm_location}")

    raw_api_key = settings.google_api_key.get_secret_value() if settings.google_api_key else ""
    if not raw_api_key:
        print("\n" + "!" * 70)
        print("❌ ERROR: GOOGLE_API_KEY is empty in backend/.env!")
        print("Please open backend/.env and set your Google API key:")
        print("   GOOGLE_API_KEY=\"AIzaSy...\"")
        print("!" * 70 + "\n")
        return False

    masked_key = raw_api_key[:6] + "..." + raw_api_key[-4:] if len(raw_api_key) > 10 else "***"
    print(f"[*] API Key Detected        : {masked_key}")

    # 2. Initialize LLM Service
    print("\n[*] Initializing Gemini LLM Service...")
    reset_llm_service()
    service = get_llm_service()
    print(f"[✓] Service instantiated: {type(service).__name__} (Model: {service.model_name})")

    # 3. Prepare Generation Prompt
    target_tool = "Veo"
    target_duration = 8
    tool_rules = get_tool_rules(target_tool)

    # Check if user passed custom prompt / idea via CLI args
    custom_idea = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None

    if custom_idea:
        spec_to_use = dict(SAMPLE_VIDEO_SPEC)
        spec_to_use["title"] = "Custom User Video Prompt"
        spec_to_use["actions"] = [
            {
                "id": "act_custom",
                "character_id": "char_sophia",
                "description": custom_idea
            }
        ]
        print(f"[*] Custom Video Idea Provided from CLI:\n    '{custom_idea}'")
    else:
        spec_to_use = SAMPLE_VIDEO_SPEC
        print(f"[*] Using Default Video Idea: 8s Luxury Apartment Penthouse Foyer with Shoes Detail")

    rendered_prompt = GENERATION_PROMPT.format(
        video_specification=json.dumps(spec_to_use, indent=2),
        total_duration=target_duration,
        target_tool=target_tool,
        tool_specific_rules=tool_rules,
    )

    print(f"[*] Prompt prepared ({len(rendered_prompt)} chars). Sending to Gemini ({service.model_name})...")

    # 4. Execute Real Call
    start_time = time.perf_counter()
    try:
        result: GenerationResult = await service.generate_structured(
            prompt=rendered_prompt,
            schema=GenerationResult,
            operation="test_real_prompt_generation",
            thread_id="test_session_real_001",
        )
    except Exception as exc:
        print(f"\n❌ API Call Failed: {exc}")
        return False

    elapsed = time.perf_counter() - start_time
    print(f"\n[✓] Prompt Generation Completed in {elapsed:.2f} seconds!")

    # 5. Display Generated Results
    print("\n" + "=" * 70)
    print("🎬 GENERATED VIDEO PROMPTS & SCENE PLAN")
    print("=" * 70)

    print(f"Total Scenes Generated: {len(result.scenes)}")
    print(f"Total Prompts/Shots   : {len(result.prompts)}")
    print(f"Total Duration Planned: {result.total_duration}s\n")

    output_lines = []
    output_lines.append(f"# Video Prompt Agent — Generated Results")
    output_lines.append(f"Model: {settings.gemini_llm_model} | Duration: {result.total_duration}s | Target: {target_tool}\n")

    for idx, prompt_item in enumerate(result.prompts, 1):
        shot_header = f"--- [SHOT {idx} of {len(result.prompts)}] (Duration: {prompt_item.duration_seconds}s) ---"
        print(shot_header)
        print(f"Shot ID    : {prompt_item.shot_id} (Scene ID: {prompt_item.scene_id})")
        print(f"\n🎥 VIDEO PROMPT TEXT:")
        print(f"{prompt_item.prompt_text}\n")
        
        if prompt_item.negative_constraints:
            print(f"⛔ Negative Constraints: {prompt_item.negative_constraints}")
        if prompt_item.continuity_requirements:
            print(f"🔗 Continuity Requirements: {', '.join(prompt_item.continuity_requirements)}")
        print("-" * 70)

        output_lines.append(shot_header)
        output_lines.append(f"Prompt Text:\n{prompt_item.prompt_text}\n")
        if prompt_item.negative_constraints:
            output_lines.append(f"Negative Constraints: {prompt_item.negative_constraints}")
        output_lines.append("\n")

    # 6. Save to File
    out_dir = backend_dir / "generated_prompts"
    out_dir.mkdir(exist_ok=True)
    
    txt_path = out_dir / "generated_video_prompt.txt"
    txt_path.write_text("\n".join(output_lines), encoding="utf-8")
    
    json_path = out_dir / "generated_video_prompt.json"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"\n💾 Saved Prompts:")
    print(f"   - Text : {txt_path}")
    print(f"   - JSON : {json_path}")
    print("=" * 70)
    print("🎉 REAL PROMPT GENERATION TEST SUCCESSFUL!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_prompt_generation_test())
    sys.exit(0 if success else 1)
