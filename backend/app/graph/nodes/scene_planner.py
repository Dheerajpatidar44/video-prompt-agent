import json
import logging
from math import isclose
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.scene_plan import MasterScenePlan, ValidationIssue, PlanStatus
from app.llm.ollama import LLMService, LLMException
from app.prompts.scene_planner import SCENE_PLANNER_PROMPT

logger = logging.getLogger(__name__)

def validate_scene_plan(spec, plan: MasterScenePlan) -> MasterScenePlan:
    issues = []
    
    # 1. Total Duration Check
    target_duration = spec.output_requirements.duration_seconds
    if target_duration is None:
        issues.append(ValidationIssue(
            issue_type="MISSING_DURATION",
            description="VideoSpecification is missing output_requirements.duration_seconds.",
            severity="CRITICAL",
            blocking=True
        ))
    else:
        # Check sum of scene durations
        sum_scenes = sum(scene.duration_seconds for scene in plan.scenes)
        if not isclose(sum_scenes, target_duration, rel_tol=1e-3, abs_tol=0.1):
            issues.append(ValidationIssue(
                issue_type="DURATION_MISMATCH",
                description=f"Sum of scenes ({sum_scenes}s) does not match target duration ({target_duration}s)",
                severity="CRITICAL",
                blocking=True
            ))
            
        # Check sum of shot durations per scene
        for scene in plan.scenes:
            sum_shots = sum(shot.duration_seconds for shot in scene.shots)
            if not isclose(sum_shots, scene.duration_seconds, rel_tol=1e-3, abs_tol=0.1):
                issues.append(ValidationIssue(
                    issue_type="SCENE_DURATION_MISMATCH",
                    description=f"Scene {scene.scene_id} shots sum ({sum_shots}s) != scene duration ({scene.duration_seconds}s)",
                    severity="CRITICAL",
                    related_entity_id=scene.scene_id,
                    blocking=True
                ))

    # 2. Action Coverage Check
    # Ensure all required actions from VideoSpecification are in at least one shot
    required_action_ids = {a.id for a in spec.actions if a.required}
    covered_action_ids = set()
    for scene in plan.scenes:
        for shot in scene.shots:
            for act_id in shot.source_actions:
                covered_action_ids.add(act_id)
                
    missing_actions = required_action_ids - covered_action_ids
    if missing_actions:
        issues.append(ValidationIssue(
            issue_type="MISSING_ACTIONS",
            description=f"The following required actions were not planned in any shot: {missing_actions}",
            severity="CRITICAL",
            blocking=True
        ))

    # 3. Continuity Reference Checks
    valid_character_ids = {c.id for c in spec.characters}
    valid_product_ids = {p.id for p in spec.products}
    valid_location_ids = {l.id for l in spec.locations}
    
    for scene in plan.scenes:
        if scene.location_id and scene.location_id not in valid_location_ids:
             issues.append(ValidationIssue(
                 issue_type="INVALID_LOCATION",
                 description=f"Scene {scene.scene_id} references unknown location {scene.location_id}",
                 severity="CRITICAL",
                 related_entity_id=scene.scene_id,
                 blocking=True
             ))
        for cid in scene.character_ids:
             if cid not in valid_character_ids:
                  issues.append(ValidationIssue(
                      issue_type="INVALID_CHARACTER",
                      description=f"Scene {scene.scene_id} references unknown character {cid}",
                      severity="CRITICAL",
                      related_entity_id=scene.scene_id,
                      blocking=True
                  ))
        for pid in scene.product_ids:
             if pid not in valid_product_ids:
                  issues.append(ValidationIssue(
                      issue_type="INVALID_PRODUCT",
                      description=f"Scene {scene.scene_id} references unknown product {pid}",
                      severity="CRITICAL",
                      related_entity_id=scene.scene_id,
                      blocking=True
                  ))

    plan.validation_issues = issues
    
    if any(issue.blocking for issue in issues):
        plan.status = PlanStatus.BLOCKED
    else:
        plan.status = PlanStatus.READY
        
    return plan

def scene_planner(state: AgentState) -> AgentState:
    logger.info("Running Scene Planner...")
    
    spec = state.get("video_specification")
    if not spec:
        return {**state, "status": AgentStatus.ERROR, "error": "No VideoSpecification found in state."}
        
    target_duration = spec.output_requirements.duration_seconds
    
    prompt = SCENE_PLANNER_PROMPT.format(
        video_specification=spec.model_dump_json(indent=2),
        continuity_bible=spec.continuity_bible.model_dump_json(indent=2),
        total_duration=target_duration if target_duration is not None else "UNKNOWN"
    )
    
    llm = LLMService()
    try:
        plan = llm.generate_structured(prompt, MasterScenePlan)
    except LLMException as e:
        logger.error(f"Failed to generate MasterScenePlan: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Run deterministic Python validation
    plan = validate_scene_plan(spec, plan)

    return {
        **state,
        "scene_plan": plan,
        "status": AgentStatus.VALIDATING
    }
