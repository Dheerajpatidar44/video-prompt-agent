INITIAL_ANALYSIS_PROMPT = """You are an expert AI Video Production Analyst and Prompt Engineer.

Perform ALL of the following tasks in a SINGLE response:

1. SCRIPT ANALYSIS — Extract every explicitly stated detail from the script.
2. GAP DETECTION — Identify missing, ambiguous, or contradictory information that would prevent generating a high-quality video prompt.
3. QUESTION GENERATION — For each CRITICAL or IMPORTANT gap, generate a clear, user-friendly clarification question.

===================
SCRIPT:
{script}
===================

ANALYSIS RULES:
- Extract ONLY explicitly stated information. Do NOT invent details.
- If something is not in the script, leave it null/empty.

GAP RULES:
- Only flag gaps that MATERIALLY affect video generation quality.
- Assign importance: CRITICAL, IMPORTANT, OPTIONAL, or INFERABLE.
- Do NOT flag trivial details (exact shoe brand, ISO value, etc.).
- Provide evidence from the script for each gap.
- Each gap needs a unique id string, category, importance, title, description, why_it_matters, evidence, and status="OPEN".
- Categories: STORY, CHARACTER, LOCATION, PRODUCT, ACTION, CAMERA, COMPOSITION, LIGHTING, VISUAL_STYLE, AUDIO, DIALOGUE, TIMING, ASPECT_RATIO, CONTINUITY, REFERENCE_ASSET, OUTPUT_REQUIREMENT, CONSTRAINT, OTHER.

QUESTION RULES:
- Generate questions ONLY for CRITICAL and IMPORTANT gaps.
- Group related gaps into a single question when logical.
- Use non-technical, user-friendly language.
- Each question needs: id, gap_ids (must match actual gap ids you generated), question, category, priority, answer_type (TEXT/SINGLE_CHOICE/MULTI_CHOICE/BOOLEAN/NUMBER), options (if applicable), required (bool).
- Keep gap_ids strictly consistent with the gaps you listed.

Return a single JSON object containing all fields for analysis, gaps, and questions.
"""
