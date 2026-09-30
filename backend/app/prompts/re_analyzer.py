RE_ANALYZER_PROMPT = """You are an expert video production analyst and prompt engineer.

Re-evaluate the script and the list of previously detected gaps in light of new answers provided by the user, and perform ALL of the following tasks in a SINGLE response:

1. GAP RE-EVALUATION — Determine which previous gaps are resolved, still open, or need updating based on the user's answers.
2. NEW GAP DETECTION — Identify any new gaps introduced by the user's answers (e.g. a contradiction, or a promised asset that is still missing).
3. QUESTION GENERATION — If requested, generate clarification questions for any gap that remains CRITICAL or IMPORTANT and OPEN.

===================
ORIGINAL SCRIPT:
{script}

ORIGINAL SCRIPT ANALYSIS:
{analysis}

PREVIOUS GAPS:
{gaps}

USER ANSWERS:
{answers}

GENERATE QUESTIONS: {generate_questions}
===================

ANALYSIS RULES:
- Treat the user's answers as authoritative new information, equal in weight to the
  original script — but never let an answer silently overwrite the original script.
  If an answer contradicts the original script, do NOT change the script; instead,
  record the contradiction (via contradiction_details) on the relevant gap, or raise
  a new gap for it.
- Do NOT invent or assume information beyond what the script, the previous analysis,
  and the user's answers actually state.
- If an answer references a new asset (e.g. "yes, I have a reference image for that")
  but the asset itself was not actually provided, raise a new gap for the missing
  reference asset rather than assuming it exists.

GAP RULES:
- STRICT SEMANTIC VALIDATION: mark a gap RESOLVED only if the answer semantically
  provides sufficient information to satisfy that specific gap. Do not mark a gap
  RESOLVED merely because a related question was answered.
  Example: if the gap is "missing duration" and the answer is "make it luxurious",
  the duration gap remains OPEN.
- If an answer is vague or insufficient (e.g. "Normal" for character appearance),
  the gap MUST remain OPEN rather than being marked RESOLVED.
- Every previous gap must be returned, whether OPEN, RESOLVED, or DISMISSED — do not
  silently drop a gap from the output.
- Keep the same id for any gap that already existed; only assign new ids to newly
  discovered gaps.
- Do NOT create multiple separate gaps for the same underlying missing detail;
  merge overlapping gaps into one before finalizing the list.
- Categories: STORY, CHARACTER, LOCATION, PRODUCT, ACTION, CAMERA, COMPOSITION, LIGHTING, VISUAL_STYLE, AUDIO, DIALOGUE, TIMING, ASPECT_RATIO, CONTINUITY, REFERENCE_ASSET, OUTPUT_REQUIREMENT, CONSTRAINT, OTHER.
- Importance: CRITICAL, IMPORTANT, OPTIONAL, or INFERABLE.
- For any gap marked INFERABLE, do not leave its value empty — populate
  inferred_value with your best reasonable inference.

QUESTION RULES:
- When GENERATE QUESTIONS is true, generate a new Question object for every gap that
  is still CRITICAL or IMPORTANT and OPEN after incorporating the user's answers.
  When GENERATE QUESTIONS is false, return an empty questions list.
- Never generate a question for a gap that the user's answers already resolved.
- Group related gaps into a single question when logical.
- Use non-technical, user-friendly language.
- Each question's gap_ids must reference actual gap id values present in the
  returned gaps list — do not leave gap_ids empty, and do not invent gap ids.

Return a JSON object containing:
- a "gaps" array, with the following fields per gap:
  - id: A unique string identifier. Keep the same id for existing gaps.
  - category: One of the categories listed above.
  - importance: One of [CRITICAL, IMPORTANT, OPTIONAL, INFERABLE].
  - title: A short title.
  - description: Clear description of the missing or ambiguous info.
  - why_it_matters: Why this affects the video prompt.
  - evidence: Quote or explain the relevant text.
  - current_value: The current ambiguous or conflicting value.
  - expected_information: What info is needed.
  - confidence: 0.0 to 1.0, how confident you are this is a meaningful gap.
  - status: "OPEN", "RESOLVED", or "DISMISSED".
  - related_entities: List of strings (e.g. character names or objects involved).
  - related_scene: The scene number or description.
  - inferred_value: A reasonable default if inferable.
  - contradiction_details: Explanation if this is a contradiction.
- a "questions" array, with the following fields per question:
  - id: A unique string identifier.
  - gap_ids: List of string IDs of the gaps this question addresses. Must strictly match the returned gap IDs.
  - question: The clarification question text.
  - category: A related category string (e.g. CHARACTER, LIGHTING).
  - priority: One of [CRITICAL, IMPORTANT, OPTIONAL, INFERABLE].
  - answer_type: One of [TEXT, SINGLE_CHOICE, MULTI_CHOICE, BOOLEAN, NUMBER].
  - options: List of string options (or null if not applicable).
  - required: Boolean, whether an answer is strictly required (usually true).
"""