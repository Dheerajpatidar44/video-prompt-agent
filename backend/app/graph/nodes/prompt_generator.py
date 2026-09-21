import logging
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.generated_prompt import PromptSet, GeneratedPrompt, PromptStatus, ValidationIssue
from app.schemas.scene_plan import PlanStatus
from app.llm.ollama import LLMService, LLMException
from app.prompts.prompt_generator import PROMPT_GENERATOR_INSTRUCTION
from app.validators.prompt_validation import validate_prompt_set

logger = logging.getLogger(__name__)

def prompt_generator(state: AgentState) -> AgentState:
    logger.info("Running Prompt Generator...")
    
    spec = state.get("video_specification")
    master_plan = state.get("scene_plan")
    
    if not spec:
        return {**state, "status": AgentStatus.ERROR, "error": "No VideoSpecification found in state."}
        
    if not master_plan:
        return {**state, "status": AgentStatus.ERROR, "error": "No ScenePlan found in state."}

    # Initialize PromptSet
    prompt_set = PromptSet(
        total_duration=master_plan.total_duration,
        aspect_ratio=spec.output_requirements.aspect_ratio
    )
    
    if master_plan.status == PlanStatus.BLOCKED:
        prompt_set.status = PromptStatus.BLOCKED
        prompt_set.validation_issues.append(ValidationIssue(
            issue_type="SCENE_PLAN_BLOCKED",
            description="Cannot generate prompts because ScenePlan is BLOCKED.",
            severity="CRITICAL",
            blocking=True
        ))
        return {**state, "prompt_set": prompt_set, "status": AgentStatus.VALIDATING}

    llm = LLMService()
    generated_prompts = []
    previous_shot_state = "None. This is the first shot."
    
    for scene in master_plan.scenes:
        for shot in scene.shots:
            # Build Context
            prompt = PROMPT_GENERATOR_INSTRUCTION.format(
                video_specification=spec.model_dump_json(indent=2),
                continuity_bible=spec.continuity_bible.model_dump_json(indent=2),
                scene_plan=scene.model_dump_json(indent=2),
                previous_shot_state=previous_shot_state,
                current_shot_plan=shot.model_dump_json(indent=2)
            )
            
            try:
                gen_prompt = llm.generate_structured(prompt, GeneratedPrompt)
                
                # Overwrite structural fields deterministically to avoid LLM hallucination of IDs
                gen_prompt.scene_id = scene.scene_id
                gen_prompt.shot_id = shot.shot_id
                gen_prompt.sequence_number = shot.shot_number
                gen_prompt.duration_seconds = shot.duration_seconds
                
                generated_prompts.append(gen_prompt)
                
                # Update previous state context for next iteration
                previous_shot_state = f"Shot {shot.shot_id} completed. Action taken: {shot.action}. Resulting state must be inherited if entities persist."
                
            except LLMException as e:
                logger.error(f"Failed to generate prompt for shot {shot.shot_id}: {e}")
                # We stop early or record a blocked state if LLM fails
                prompt_set.status = PromptStatus.BLOCKED
                prompt_set.validation_issues.append(ValidationIssue(
                    issue_type="LLM_FAILURE",
                    description=f"LLM generation failed for shot {shot.shot_id}: {str(e)}",
                    severity="CRITICAL",
                    blocking=True
                ))
                return {**state, "prompt_set": prompt_set, "status": AgentStatus.VALIDATING}

    prompt_set.prompts = generated_prompts
    
    # Run deterministic Python validation
    prompt_set = validate_prompt_set(spec, master_plan, prompt_set)

    return {
        **state,
        "prompt_set": prompt_set,
        "status": AgentStatus.VALIDATING
    }
