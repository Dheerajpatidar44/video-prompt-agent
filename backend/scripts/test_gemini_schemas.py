"""Phase 0: Gemini Schema Compatibility Test.

Sends all 5 production Pydantic schemas to Gemini with response_schema
to verify API-level schema acceptance and structured output generation:
1. InitialAnalysisResult (Script Analysis)
2. VideoSpecification (Specs & Continuity Bible)
3. GenerationResult (Scene plans & Prompts)
4. ReAnalysisResult (Gap updates & Q&A)
5. PromptPatchResult (Targeted Prompt Corrections)
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from google import genai
from google.genai import types
from app.core.config import settings
from app.core.google_client import create_genai_client

from app.schemas.script import InitialAnalysisResult
from app.schemas.specification import VideoSpecification
from app.schemas.generation import GenerationResult
from app.schemas.agent import ReAnalysisResult
from app.prompts.prompt_patch import PromptPatchResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_gemini_schemas")

# Tell pytest to ignore this standalone executable script
__test__ = False


def get_test_client() -> genai.Client:
    """Initialize client using existing settings."""
    return create_genai_client(location=settings.gemini_llm_location)


async def verify_single_schema(client: genai.Client, model_id: str, name: str, schema_cls, sample_prompt: str):
    logger.info(f"--- Testing Schema: {name} ({schema_cls.__name__}) ---")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema_cls,
        temperature=0.2,
        max_output_tokens=4096,
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_id,
            contents=sample_prompt,
            config=config,
        )

        candidate = response.candidates[0] if response and response.candidates else None
        if not candidate:
            logger.error(f"[FAIL] {name}: No candidates returned.")
            return False, "No candidates returned"

        finish_reason = getattr(candidate, "finish_reason", None)
        logger.info(f"Finish reason: {finish_reason}")

        raw_text = response.text
        if not raw_text:
            logger.error(f"[FAIL] {name}: Response text is empty. Finish reason: {finish_reason}")
            return False, f"Empty text (finish_reason={finish_reason})"

        # Validate with Pydantic
        parsed = schema_cls.model_validate_json(raw_text)
        logger.info(f"[SUCCESS] {name} successfully generated and validated! Sample type: {type(parsed)}")
        return True, None

    except Exception as exc:
        logger.error(f"[FAIL] {name}: {exc}")
        return False, str(exc)


async def main():
    client = get_test_client()
    model_id = os.environ.get("GEMINI_LLM_MODEL", "gemini-2.5-flash")
    logger.info(f"Target LLM Model ID: {model_id}")

    test_cases = [
        (
            "PromptPatchResult",
            PromptPatchResult,
            "Fix the prompt: 'A woman in red dress walks in room' to have correct lighting.",
        ),
        (
            "ReAnalysisResult",
            ReAnalysisResult,
            "Re-evaluate gaps for script: 'A detective enters a dark alley.' User answer: 'The detective is named John, age 45.'",
        ),
        (
            "InitialAnalysisResult",
            InitialAnalysisResult,
            "Perform initial analysis of script: 'A coffee commercial showing a steaming mug on a wooden table at sunrise.'",
        ),
        (
            "GenerationResult",
            GenerationResult,
            "Generate 1 scene and 1 shot prompt for a 4-second video about a car driving on a coastal road at sunset.",
        ),
        (
            "VideoSpecification",
            VideoSpecification,
            "Draft a VideoSpecification for a 10s perfume commercial featuring a woman in a glass greenhouse.",
        ),
    ]

    results = {}
    for name, schema_cls, prompt in test_cases:
        ok, err = await verify_single_schema(client, model_id, name, schema_cls, prompt)
        results[name] = {"passed": ok, "error": err}

    print("\n" + "=" * 60)
    print("SCHEMA COMPATIBILITY SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, res in results.items():
        status = "PASSED" if res["passed"] else "FAILED"
        print(f"{name:25}: {status}")
        if not res["passed"]:
            all_passed = False
            print(f"   Error: {res['error']}")
    print("=" * 60)

    if all_passed:
        print("ALL 5 SCHEMAS FULLY COMPATIBLE WITH GEMINI!")
    else:
        print("SOME SCHEMAS REQUIRE NORMALIZATION BEFORE DEPLOYMENT.")


if __name__ == "__main__":
    asyncio.run(main())
