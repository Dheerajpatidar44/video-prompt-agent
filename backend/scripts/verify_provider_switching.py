"""Test script to verify provider switching between Gemini, Claude, and Mock."""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Clear TESTING env var so we test real provider selection
os.environ.pop("TESTING", None)

from app.core.config import settings
from app.llm import get_llm_service, reset_llm_service

print("=" * 60)
print("TESTING PROVIDER SELECTION")
print("=" * 60)

# Case 1: Gemini Provider
settings.llm_provider = "gemini"
reset_llm_service()
service_gemini = get_llm_service()
print(f"1. Selected 'gemini' -> Active service type: {type(service_gemini).__name__}")
assert type(service_gemini).__name__ == "GeminiLLMService"

# Case 2: Claude Provider
settings.llm_provider = "claude"
reset_llm_service()
service_claude = get_llm_service()
print(f"2. Selected 'claude' -> Active service type: {type(service_claude).__name__}")
assert type(service_claude).__name__ == "ClaudeLLMService"

# Case 3: Mock Provider (CI mode)
os.environ["TESTING"] = "1"
reset_llm_service()
service_mock = get_llm_service()
print(f"3. TESTING=1 mode   -> Active service type: {type(service_mock).__name__}")
assert type(service_mock).__name__ == "MockLLMService"

print("=" * 60)
print("ALL PROVIDER SWITCHING CHECKS PASSED PERFECTLY!")
print("=" * 60)

