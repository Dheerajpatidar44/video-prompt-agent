"""Combined scene planning + prompt generation node.

ONE LLM call produces both the scene plan and all prompts.
This replaces the old scene_planner → prompt_generator (N calls per shot) chain.
"""
import logging
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.scene_plan import (
    MasterScenePlan, ScenePlan, ShotPlan, PlanStatus,
    TransitionType, NarrativeRole, ValidationIssue,
)
from app.schemas.generated_prompt import (
    PromptSet, GeneratedPrompt, PromptStatus,
    ValidationIssue as PromptValidationIssue,
)
from app.schemas.generation import GenerationResult
from app.llm.ollama import llm_service, LLMException
from app.prompts.generation import GENERATION_PROMPT
from app.validators.prompt_validation import validate_prompt_set

logger = logging.getLogger(__name__)


async def generate_scenes_and_prompts(state: AgentState) -> AgentState:
    """ONE LLM call: scene planning + prompt generation."""
    logger.info("Running combined Scene Planner + Prompt Generator...")

    spec = state.get("video_specification")
    thread_id = state.get("project_id", "")

    if not spec:
        return {
            **state,
            "status": AgentStatus.ERROR,
            "error": "No VideoSpecification found in state.",
        }

    target_duration = spec.output_requirements.duration_seconds

    prompt = GENERATION_PROMPT.format(
        video_specification=spec.model_dump_json(indent=2),
        continuity_bible=spec.continuity_bible.model_dump_json(indent=2),
        total_duration=target_duration if target_duration is not None else "UNKNOWN",
    )

    try:
        result = await llm_service.generate_structured(
            prompt,
            GenerationResult,
            operation="generate_scenes_and_prompts",
            thread_id=thread_id,
            num_predict=4096,  # larger output for combined generation
        )
    except LLMException as e:
        logger.error(f"Failed to generate scenes+prompts: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # ---- Deterministic Python post-processing ----

    # 1. Convert GenerationResult scenes → MasterScenePlan
    scene_plans = []
    for gs in result.scenes:
        shots = []
        for sh in gs.shots:
            shots.append(
                ShotPlan(
                    shot_id=sh.shot_id,
                    shot_number=sh.shot_number,
                    scene_id=gs.scene_id,
                    start_time=sh.start_time,
                    end_time=sh.end_time,
                    duration_seconds=sh.duration_seconds,
                    purpose=sh.purpose,
                    subject=sh.subject,
                    action=sh.action,
                    framing=sh.framing,
                    camera_angle=sh.camera_angle,
                    camera_movement=sh.camera_movement,
                    composition=sh.composition,
                    lighting=sh.lighting,
                    visual_focus=sh.visual_focus,
                    product_focus=sh.product_focus,
                    source_actions=sh.source_actions,
                )
            )

        try:
            narrative = NarrativeRole(gs.narrative_role)
        except ValueError:
            narrative = NarrativeRole.ACTION

        scene_plans.append(
            ScenePlan(
                scene_id=gs.scene_id,
                scene_number=gs.scene_number,
                title=gs.title,
                purpose=gs.purpose,
                narrative_role=narrative,
                start_time=gs.start_time,
                end_time=gs.end_time,
                duration_seconds=gs.duration_seconds,
                location_id=gs.location_id,
                character_ids=gs.character_ids,
                product_ids=gs.product_ids,
                shots=shots,
            )
        )

    master_plan = MasterScenePlan(
        scenes=scene_plans,
        total_duration=result.total_duration,
        status=PlanStatus.READY,
    )

    # 2. Convert GenerationResult prompts → PromptSet
    gen_prompts = []
    for gp in result.prompts:
        gen_prompts.append(
            GeneratedPrompt(
                prompt_id=gp.prompt_id,
                scene_id=gp.scene_id,
                shot_id=gp.shot_id,
                sequence_number=gp.sequence_number,
                duration_seconds=gp.duration_seconds,
                prompt_text=gp.prompt_text,
                negative_constraints=gp.negative_constraints,
                continuity_requirements=gp.continuity_requirements,
                source_actions=gp.source_actions,
            )
        )

    prompt_set = PromptSet(
        prompts=gen_prompts,
        total_duration=master_plan.total_duration,
        aspect_ratio=spec.output_requirements.aspect_ratio,
    )

    # 3. Run deterministic Python validation
    prompt_set = validate_prompt_set(spec, master_plan, prompt_set)

    return {
        **state,
        "scene_plan": master_plan,
        "prompt_set": prompt_set,
        "status": AgentStatus.VALIDATING,
    }
