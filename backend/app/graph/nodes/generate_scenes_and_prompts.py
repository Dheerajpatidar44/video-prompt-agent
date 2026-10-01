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
from app.llm.claude_client import llm_service, LLMException
from app.prompts.generation import GENERATION_PROMPT
from app.prompts.tool_rules import get_tool_rules
from app.validators.prompt_validation import validate_prompt_set

logger = logging.getLogger(__name__)


def _collect_entity_sources(spec, character_ids=None, location_id=None, product_ids=None) -> list[str]:
    """Pull the `source` tag (USER/SCRIPT/REFERENCE_IMAGE/INFERRED/SYSTEM_DEFAULT)
    off every specification entity relevant to a shot, so each generated prompt
    can carry forward where its key visual details actually came from.

    Defensive by design: specs, entities, or `source` fields may be missing or
    shaped differently depending on how VideoSpecification evolves, so every
    lookup degrades to "skip" rather than raising.
    """  
    sources: set[str] = set()

    def _add_source(entity) -> None:
        if entity is None:
            return
        src = getattr(entity, "source", None)
        if src:
            sources.add(str(src))

    characters = getattr(spec, "characters", None) or []
    locations = getattr(spec, "locations", None) or []
    products = getattr(spec, "products", None) or []

    if character_ids:
        for cid in character_ids:
            _add_source(next((c for c in characters if getattr(c, "id", None) == cid), None))

    if location_id:
        _add_source(next((l for l in locations if getattr(l, "id", None) == location_id), None))

    if product_ids:
        for pid in product_ids:
            _add_source(next((p for p in products if getattr(p, "id", None) == pid), None))

    return sorted(sources)


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
    tool = state.get("selected_tool", "Veo")
    tool_rules = get_tool_rules(tool)

    prompt = GENERATION_PROMPT.format(
        video_specification=spec.model_dump_json(indent=2),
        total_duration=target_duration if target_duration is not None else "UNKNOWN",
        target_tool=tool,
        tool_specific_rules=tool_rules,
    )
    logger.info(f"Final prompt length: {len(prompt)} characters (Tool: {tool})")

    try:
        result = await llm_service.generate_structured(
            prompt,
            GenerationResult,
            operation="generate_scenes_and_prompts",
            thread_id=thread_id,
        )
    except LLMException as e:
        logger.error(f"Failed to generate scenes+prompts: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    if not result.scenes or not result.prompts:
        error_msg = "LLM returned an empty scene/prompt plan — no scenes or prompts were generated."
        logger.error(error_msg)
        return {**state, "status": AgentStatus.ERROR, "error": error_msg}

    # ---- Deterministic Python post-processing ----

    # 1. Convert GenerationResult scenes → MasterScenePlan
    scene_plans = []
    # scene_id -> scene, used below to resolve each shot's location/character/product
    # context when building source_traceability for its prompt.
    scene_by_id = {}

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
        scene_by_id[gs.scene_id] = gs

    master_plan = MasterScenePlan(
        scenes=scene_plans,
        total_duration=result.total_duration,
        status=PlanStatus.READY,
    )

    # 2. Convert GenerationResult prompts → PromptSet
    gen_prompts = []
    for gp in result.prompts:
        gs = scene_by_id.get(gp.scene_id)
        source_traceability = _collect_entity_sources(
            spec,
            character_ids=getattr(gs, "character_ids", None) if gs else None,
            location_id=getattr(gs, "location_id", None) if gs else None,
            product_ids=getattr(gs, "product_ids", None) if gs else None,
        )

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
                source_traceability=source_traceability,
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

    if prompt_set.status == PromptStatus.READY:
        final_status = AgentStatus.COMPLETED
    else:
        final_status = AgentStatus.VALIDATING

    return {
        **state,
        "scene_plan": master_plan,
        "prompt_set": prompt_set,
        "status": final_status,
    }