import re
from typing import List, Dict, Any
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet, ValidationIssue, PromptStatus
from app.schemas.specification import VideoSpecification
from app.schemas.scene_plan import MasterScenePlan, ShotPlan, PlanStatus
from math import isclose

HALLUCINATED_CAMERA_PARAMS = [
    r"\bISO\s*\d+\b",
    r"\bf/\d+(\.\d+)?\b",
    r"\b\d+mm\b",
    r"\bshutter speed\b",
    r"\baperture\b",
    r"\bsensor size\b"
]

def validate_prompt_set(
    spec: VideoSpecification,
    master_plan: MasterScenePlan,
    prompt_set: PromptSet
) -> PromptSet:
    
    issues: List[ValidationIssue] = []
    
    if master_plan.status == PlanStatus.BLOCKED:
        issues.append(ValidationIssue(
            issue_type="SCENE_PLAN_BLOCKED",
            description="Cannot generate valid prompts because the ScenePlan is BLOCKED.",
            severity="CRITICAL",
            blocking=True
        ))
        prompt_set.validation_issues = issues
        prompt_set.status = PromptStatus.BLOCKED
        return prompt_set

    # Ensure Prompt count matches ShotPlan count
    expected_shot_ids = []
    shot_map: Dict[str, ShotPlan] = {}
    for scene in master_plan.scenes:
        for shot in scene.shots:
            expected_shot_ids.append(shot.shot_id)
            shot_map[shot.shot_id] = shot
            
    generated_shot_ids = [p.shot_id for p in prompt_set.prompts]
    
    missing_shots = set(expected_shot_ids) - set(generated_shot_ids)
    if missing_shots:
         issues.append(ValidationIssue(
             issue_type="MISSING_PROMPT",
             description=f"Missing prompts for shots: {missing_shots}",
             severity="CRITICAL",
             blocking=True
         ))
         
    # Duplicate prompt IDs
    prompt_ids = [p.prompt_id for p in prompt_set.prompts]
    if len(prompt_ids) != len(set(prompt_ids)):
         issues.append(ValidationIssue(
             issue_type="DUPLICATE_PROMPT_ID",
             description="Duplicate prompt IDs detected.",
             severity="CRITICAL",
             blocking=True
         ))
    
    # Check individual prompts
    for i, prompt in enumerate(prompt_set.prompts):
        if not prompt.prompt_text or not prompt.prompt_text.strip():
             issues.append(ValidationIssue(
                 issue_type="EMPTY_PROMPT",
                 description=f"Prompt for shot {prompt.shot_id} is empty.",
                 severity="CRITICAL",
                 related_entity_id=prompt.shot_id,
                 blocking=True
             ))
             
        if prompt.shot_id not in shot_map:
             issues.append(ValidationIssue(
                 issue_type="INVALID_SHOT_REFERENCE",
                 description=f"Prompt references unknown shot_id {prompt.shot_id}",
                 severity="CRITICAL",
                 related_entity_id=prompt.shot_id,
                 blocking=True
             ))
             continue
             
        target_shot = shot_map[prompt.shot_id]
        
        # Duration check
        if not isclose(prompt.duration_seconds, target_shot.duration_seconds, rel_tol=1e-3, abs_tol=0.1):
             issues.append(ValidationIssue(
                 issue_type="DURATION_MISMATCH",
                 description=f"Prompt duration ({prompt.duration_seconds}) != ShotPlan duration ({target_shot.duration_seconds})",
                 severity="CRITICAL",
                 related_entity_id=prompt.shot_id,
                 blocking=True
             ))
             
        # Source actions check
        missing_actions = set(target_shot.source_actions) - set(prompt.source_actions)
        if missing_actions:
             issues.append(ValidationIssue(
                 issue_type="MISSING_SOURCE_ACTIONS",
                 description=f"Prompt missing required source actions from ShotPlan: {missing_actions}",
                 severity="CRITICAL",
                 related_entity_id=prompt.shot_id,
                 blocking=True
             ))
             
        # Detect hallucinated camera parameters
        prompt_lower = prompt.prompt_text.lower()
        spec_camera_str = ""
        if spec.camera:
            spec_camera_str = str(spec.camera.model_dump()).lower()
            
        for pattern in HALLUCINATED_CAMERA_PARAMS:
            match = re.search(pattern, prompt.prompt_text, re.IGNORECASE)
            if match:
                matched_text = match.group(0).lower()
                # Check if it was explicitly requested in the VideoSpecification camera block
                if matched_text not in spec_camera_str:
                     issues.append(ValidationIssue(
                         issue_type="UNSUPPORTED_CAMERA_PARAMETER",
                         description=f"Prompt {prompt.shot_id} hallucinated technical camera parameter: '{matched_text}'",
                         severity="CRITICAL",
                         related_entity_id=prompt.shot_id,
                         blocking=True
                     ))
                     
        # Scene/Shot order check
        if expected_shot_ids and prompt.shot_id in expected_shot_ids:
            expected_index = expected_shot_ids.index(prompt.shot_id)
            if i != expected_index:
                 issues.append(ValidationIssue(
                     issue_type="ORDER_MISMATCH",
                     description=f"Prompt for shot {prompt.shot_id} is out of order.",
                     severity="CRITICAL",
                     related_entity_id=prompt.shot_id,
                     blocking=True
                 ))

    # Total duration match
    if not isclose(prompt_set.total_duration, master_plan.total_duration, rel_tol=1e-3, abs_tol=0.1):
         issues.append(ValidationIssue(
             issue_type="TOTAL_DURATION_MISMATCH",
             description=f"PromptSet duration ({prompt_set.total_duration}) != MasterScenePlan duration ({master_plan.total_duration})",
             severity="CRITICAL",
             blocking=True
         ))
         
    prompt_set.validation_issues = issues
    
    if any(issue.blocking for issue in issues):
        prompt_set.status = PromptStatus.BLOCKED
    else:
        prompt_set.status = PromptStatus.READY
        
    return prompt_set
