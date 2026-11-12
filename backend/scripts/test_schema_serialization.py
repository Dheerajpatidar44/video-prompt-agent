"""Offline schema conversion test for Google GenAI SDK.
Verifies that all 5 Pydantic schemas can be converted into OpenAPI 3.0 schema
dictionaries by google.genai without syntax or structure errors.
"""
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from google.genai import types
from app.schemas.script import InitialAnalysisResult
from app.schemas.specification import VideoSpecification
from app.schemas.generation import GenerationResult
from app.schemas.agent import ReAnalysisResult
from app.prompts.prompt_patch import PromptPatchResult

schemas = [
    ("PromptPatchResult", PromptPatchResult),
    ("ReAnalysisResult", ReAnalysisResult),
    ("InitialAnalysisResult", InitialAnalysisResult),
    ("GenerationResult", GenerationResult),
    ("VideoSpecification", VideoSpecification),
]

print("=" * 60)
print("OFFLINE SCHEMA CONVERSION CHECK (google.genai)")
print("=" * 60)

for name, cls in schemas:
    try:
        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=cls,
        )
        print(f"[OK] {name:25}: Converted successfully into GenerateContentConfig")
    except Exception as e:
        print(f"[FAIL] {name:25}: {e}")

print("=" * 60)

