"""Review Prompts node — runs after generate_scenes_and_prompts.

Performs deterministic QA checks on the generated PromptSet, auto-fixes
what it can, and uses targeted LLM patches for remaining BLOCKERs.
Never blocks on human input — always resolves to a COMPLETED status.
"""
import logging 
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.validators.prompt_reviewer import PromptReviewer
from app.validators.prompt_corrector import apply_corrections
from app.llm.claude_client import llm_service

logger = logging.getLogger(__name__)


async def review_prompts(state: AgentState) -> AgentState:
    """Runs after generate_scenes_and_prompts.  Reviews and, if needed,
    corrects the prompt_set in place.  Never blocks on human input."""
    spec = state.get("video_specification")
    scene_plan = state.get("scene_plan")
    prompt_set = state.get("prompt_set")
    original_script = state.get("original_script", "")
    selected_tool = state.get("selected_tool", "Veo")

    if not spec or not scene_plan or not prompt_set:
        logger.error("review_prompts: missing spec, scene_plan, or prompt_set in state.")
        return {
            **state,
            "status": AgentStatus.COMPLETED,
        }

    # Run all deterministic QA checks
    reviewer = PromptReviewer(
        spec=spec,
        scene_plan=scene_plan,
        prompt_set=prompt_set,
        original_script=original_script,
        selected_tool=selected_tool,
    )
    report = reviewer.run_all_checks()

    logger.info(
        f"Prompt review complete: {len(report.issues)} issues found "
        f"(BLOCKER={report.stats.get('issues_by_severity', {}).get('BLOCKER', 0)}, "
        f"WARNING={report.stats.get('issues_by_severity', {}).get('WARNING', 0)})"
    )

    # Apply corrections (auto-fix + targeted LLM patches if needed)
    corrected_prompt_set, final_report = await apply_corrections(
        prompt_set, report, spec, llm_service,
    )

    logger.info(
        f"Prompt correction complete: status={final_report.status.value}, "
        f"fixes_applied={len(final_report.fixes_applied)}, "
        f"llm_retries={final_report.retries_used}"
    )

    return {
        **state,
        "prompt_set": corrected_prompt_set,
        "review_report": final_report,          
        "status": AgentStatus.COMPLETED,
    }
