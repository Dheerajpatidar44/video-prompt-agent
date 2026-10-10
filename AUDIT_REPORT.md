# Project Audit Report

## 1. Executive Summary
The system is highly robust, fully typed, and cleanly structured using a modern FastAPI/LangGraph backend and React/Next.js frontend. The pipeline correctly handles complex multi-step state and deterministic QA (Reviewer Agent) successfully prevents regressions without uncontrolled LLM loops. The top 3 risks are: (1) Misconfigured API credentials blocking all generation, (2) Output requirement inputs missing from the API endpoints despite prompts supporting them, and (3) Hardcoded fuzzy logic in the prompt corrector that may aggressively deduplicate valid constraints.

## 2. Findings by Severity

### CRITICAL (breaks functionality or causes silent data loss/corruption)
- **File:** `backend/.env` (and `app/core/config.py`)
  - **Issue:** `ANTHROPIC_API_KEY` is empty, and `ANTHROPIC_MODEL` contains a typo (`claude-sonet-5-5`).
  - **Why it matters:** Any real end-to-end test will instantly crash with an `anthropic.AuthenticationError` (HTTP 500) because the key is empty and the model name is invalid.
  - **Fix Needed:** Update `.env` with a real key and valid model name (e.g., `claude-3-5-sonnet-20240620`) before attempting production testing.

### HIGH (real bug or design drift, not yet causing visible failure but will)
- **File:** `backend/app/api/routes/scripts.py` (lines 101-109) & `backend/app/graph/nodes/build_video_spec.py` (line 31)
  - **Issue:** The `/analyze` API endpoint does not accept `duration` or `aspect_ratio` form fields. Consequently, `build_video_spec.py` hardcodes `output_requirements="None specified by user."`.
  - **Why it matters:** The user is forced into system defaults without knowing, and the LLM prompt's capability to respect user output requirements is bypassed entirely. This breaks the API contract intent.
  - **Fix Needed:** Add `duration` and `aspect_ratio` as optional form fields in the FastAPI route and inject them into `initial_state` so `build_video_spec` can utilize them.

### MEDIUM (quality, consistency, or maintainability issue)
- **File:** `backend/app/validators/prompt_corrector.py` (line 83)
  - **Issue:** Hardcoded fuzzy matching threshold: `fuzz.token_set_ratio(s, kept) > 75` for negative constraint deduplication.
  - **Why it matters:** A 75% threshold is quite low. It might mistakenly deduplicate sentences that share vocabulary but carry semantically different negative constraints.
  - **Fix Needed:** Increase the threshold to a safer margin (e.g., 85-90) or make it configurable in settings.

- **File:** `frontend/src/app/page.tsx`
  - **Issue:** No UI inputs exist for `duration` and `aspect_ratio`.
  - **Why it matters:** Users cannot specify their desired video length or format, forcing reliance on fallback backend defaults.
  - **Fix Needed:** Add form controls (dropdowns/sliders) in the `ScriptInput` or `VideoToolSelector` component to capture these preferences before generating.

### LOW / NOTE (minor, cosmetic, or "worth knowing" observations)
- **File:** `backend/app/graph/nodes/re_analyze.py` (line 16)
  - **Issue:** Uses `gap.title.lower().strip()` for deduplication, assuming `title` is always a valid string.
  - **Why it matters:** It is safe because Pydantic provides a default string, but slightly brittle if schemas evolve to allow `None`.
  - **Fix Needed:** Use a safe getter or fallback `(getattr(gap, "title") or "").lower().strip()`.

## 3. Findings by Area

| Area | # Critical | # High | # Medium | # Low |
| :--- | :--- | :--- | :--- | :--- |
| Backend Core/Config | 1 | 0 | 0 | 0 |
| Frontend/API Contract | 0 | 1 | 1 | 0 |
| LangGraph Nodes | 0 | 0 | 0 | 1 |
| Prompt Reviewer | 0 | 0 | 1 | 0 |
| Tests | 0 | 0 | 0 | 0 |

## 4. Data Flow Map (as found, not as intended)
1. **Frontend Input:** Script (TXT/PDF) or Text + Tool + Images → Frontend `ScriptInput`/`ReferenceUploads`
2. **Ingestion:** `POST /scripts/analyze` → Uploads images to Cloudinary (returns URLs) → Extracts script text → LangGraph State (`initial_state`)
3. **Graph Start:** `analyze_script` (LLM call with vision if images) → Returns `analysis`, `gaps`, `questions`
4. **Q&A Loop:** Frontend UI `QuestionsView` → User answers → `POST /scripts/{thread_id}/answers` → `update_state` → `re_analyze` (LLM evaluates answers, conditionally generates more questions).
5. **Spec Generation:** `build_video_spec` (LLM generates spec). **[BROKEN LINK: output_requirements (duration/aspect ratio) are entirely ignored and hardcoded to NONE].**
6. **Prompt Generation:** `generate_scenes_and_prompts` (LLM generates scene plan + prompts) → Sets status `REVIEWING`.
7. **Review Agent:** `review_prompts` (Deterministic Python fixes + bounded LLM patch limit of 6).
8. **Frontend Rendering:** `useVideoAgent` polling resolves `COMPLETED` → `ResultsView` renders `scene_plan`, `prompt_set`, and `review_report`.

## 5. Test Coverage Summary
- **Backend Nodes / State:** **Well-covered**. Extensively tested in `test_phase3.py`, `test_phase5_6.py`, and `test_phase7.py`.
- **Reviewer Agent:** **Well-covered**. Tested in `test_prompt_reviewer.py` handling structural checks, content quality, continuity drift, and invariants.
- **Frontend State Management:** **Untested**. No unit tests (e.g., Jest/RTL) or E2E tests exist for `useVideoAgent` polling and UI transitions.
- **Config & Integrations:** **Mocked, masking issues**. Cloudinary and Claude API keys are mocked during tests, which hides the real `.env` misconfiguration that will crash the live app.

## 6. Recommended Next Actions
1. **Fix .env Configuration:** Set a valid Anthropic API key and model name (`claude-3-5-sonnet-20240620`) in `.env` to prevent immediate HTTP 500 crashes during the first real test.
2. **Expose Output Requirements:** Add `duration` and `aspect_ratio` inputs in the frontend and pass them through `scripts.py` to `build_video_spec.py` to give users control over video format.
3. **Review Fuzzy Logic Threshold:** Adjust the `token_set_ratio` in `prompt_corrector.py` to prevent aggressive deduplication of negative constraints.
