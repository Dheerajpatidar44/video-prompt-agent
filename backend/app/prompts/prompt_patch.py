"""Prompt patch template for targeted single-shot LLM corrections.

This template is used ONLY when the deterministic reviewer finds a BLOCKER
issue that cannot be resolved by Python auto-fix (e.g. continuity drift,
dialogue-duration mismatch).  It asks the LLM to make the minimal edit
needed to resolve the stated issue — never a creative rewrite.
"""
from pydantic import BaseModel
from typing import Optional


PROMPT_PATCH_PROMPT = """You are a video-prompt copy editor. You are given a SINGLE shot's
prompt_text (and its negative_constraints) that has a specific quality issue.
Your job is to make the MINIMAL edit needed to fix the stated issue, preserving
everything else about the prompt verbatim.

===================
CURRENT PROMPT TEXT:
{prompt_text}

CURRENT NEGATIVE CONSTRAINTS:
{negative_constraints}
 
===================
ISSUE TO FIX:
Category: {issue_category}
Message: {issue_message}
Detected value: {detected_value}
Expected value: {expected_value}

===================
RELEVANT CONTEXT (from the Video Specification / Continuity Bible):
{continuity_context}

===================
RULES:
- Fix ONLY the stated issue.  Do not rewrite, expand, or creatively enhance the prompt.
- If the issue is about a character/product description drifting, correct the
  description to match the canonical continuity details provided above.
- If the issue is about dialogue timing (too many words for the shot duration),
  shorten the dialogue while preserving meaning.
- Preserve the natural, cinematic sentence style of the original prompt.
- Return the corrected prompt_text and negative_constraints.  If negative_constraints
  does not need changing, return it as-is.
"""


class PromptPatchResult(BaseModel):
    """Minimal response schema for a single-shot prompt correction."""
    prompt_text: str
    negative_constraints: Optional[str] = None
