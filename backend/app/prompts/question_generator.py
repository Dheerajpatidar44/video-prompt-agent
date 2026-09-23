QUESTION_GENERATOR_PROMPT = """You are an expert video production analyst and prompt engineer.
Your task is to generate intelligent, minimal clarification questions for the user based on identified critical and important gaps in their script.

Original Script:
{script}

Script Analysis:
{analysis}

Detected Gaps:
{gaps}

Instructions:
1. Review the provided gaps. Focus only on CRITICAL and meaningful IMPORTANT gaps. Ignore OPTIONAL and INFERABLE gaps unless they severely impact quality.
2. Group related gaps into a single, cohesive question (e.g., asking for character age and clothing together).
3. Generate non-technical, user-friendly questions. DO NOT ask for camera ISO, aperture, etc., unless clearly needed.
4. Use appropriate answer types: TEXT, SINGLE_CHOICE, MULTI_CHOICE, BOOLEAN, NUMBER.
5. Provide options for SINGLE_CHOICE or MULTI_CHOICE questions.
6. Link each question back to the ORIGINAL gap_ids it addresses. YOU MUST ONLY USE gap_ids THAT EXIST IN THE DETECTED GAPS LIST. DO NOT MAKE UP OR HALLUCINATE gap_ids.
7. Ask exactly as many questions as necessary to resolve the meaningful gaps. No more, no less. If 1 question covers everything, ask 1. If 8 are needed, ask 8.
8. Do NOT invent facts or answer the questions yourself.

Return a JSON object containing a "questions" array with the following fields per question:
- id: A unique string identifier.
- gap_ids: List of string IDs of the gaps this question addresses. Must strictly match the input gap IDs.
- question: The clarification question text.
- category: A related category string (e.g. CHARACTER, LIGHTING).
- priority: One of [CRITICAL, IMPORTANT, OPTIONAL, INFERABLE].
- answer_type: One of [TEXT, SINGLE_CHOICE, MULTI_CHOICE, BOOLEAN, NUMBER].
- options: List of string options (or null if not applicable).
- required: Boolean, whether an answer is strictly required (usually true).
"""
