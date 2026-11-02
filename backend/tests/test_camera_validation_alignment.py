import pytest
from app.prompts.generation import GENERATION_PROMPT
from app.prompts.tool_rules import get_tool_rules
from app.validators.prompt_validation import validate_prompt_set, HALLUCINATED_CAMERA_PARAMS
from app.schemas.specification import VideoSpecification, OutputRequirements, CharacterSpec
from app.schemas.scene_plan import MasterScenePlan, ScenePlan, ShotPlan, NarrativeRole
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet, PromptStatus


def test_tool_rules_does_not_contain_35mm_trigger():
    """Ensure tool_rules.py does not contain '35mm' which triggers regex r'\\b\\d+mm\\b'."""
    rules = get_tool_rules("Veo")
    assert "35mm" not in rules
    assert "50mm" not in rules


def test_generation_prompt_contains_strict_camera_validation_rule():
    """Ensure generation.py explicitly warns against numeric focal lengths and f-stops."""
    assert "STRICT CAMERA VALIDATION RULE" in GENERATION_PROMPT
    assert "NEVER output numeric lens focal lengths" in GENERATION_PROMPT
    assert "shallow depth of field" in GENERATION_PROMPT


def test_qualitative_camera_prompts_pass_validation():
    """Verify that qualitative cinematic descriptions pass validation cleanly without being blocked."""
    spec = VideoSpecification(
        project_id="test-qualitative",
        characters=[CharacterSpec(id="char_1", name="Model")],
        output_requirements=OutputRequirements(duration_seconds=6),
    )

    shot = ShotPlan(
        shot_id="shot_01",
        shot_number=1,
        scene_id="scene_01",
        start_time=0.0,
        end_time=6.0,
        duration_seconds=6.0,
        purpose="Intro hero shot",
        subject="Model wearing elegant attire",
        action="Walks towards the camera slowly",
        source_actions=["walks"],
    )

    scene = ScenePlan(
        scene_id="scene_01",
        scene_number=1,
        title="Opening",
        purpose="Establish hero",
        narrative_role=NarrativeRole.ESTABLISHING,
        start_time=0.0,
        end_time=6.0,
        duration_seconds=6.0,
        shots=[shot],
    )

    master_plan = MasterScenePlan(
        project_id="test-qualitative",
        scenes=[scene],
        total_duration=6.0,
    )

    # Prompt with qualitative cinematic language (no numbers like 35mm or f/1.8)
    prompt = GeneratedPrompt(
        prompt_id="prompt_01",
        scene_id="scene_01",
        shot_id="shot_01",
        sequence_number=1,
        duration_seconds=6.0,
        prompt_text=(
            "Slow push-in camera movement tracking the model walking gracefully forward. "
            "Shallow depth of field with sharp subject focus and soft, diffused background separation. "
            "Natural morning sunlight with soft golden rim lighting and analog film grain texture."
        ),
        negative_constraints="unnatural movement, morphing, face distortion",
        source_actions=["walks"],
    )

    prompt_set = PromptSet(
        project_id="test-qualitative",
        prompts=[prompt],
        total_duration=6.0,
    )

    validated = validate_prompt_set(spec, master_plan, prompt_set, target_tool="Veo")
    
    # Check that there are zero camera parameter issues
    camera_issues = [issue for issue in validated.validation_issues if issue.issue_type == "UNSUPPORTED_CAMERA_PARAMETER"]
    assert len(camera_issues) == 0
    assert validated.status != PromptStatus.BLOCKED


def test_numeric_camera_prompts_are_caught():
    """Verify that prompts containing forbidden numeric lens parameters are caught by the validator."""
    spec = VideoSpecification(
        project_id="test-numeric",
        characters=[CharacterSpec(id="char_1", name="Model")],
        output_requirements=OutputRequirements(duration_seconds=6),
    )

    shot = ShotPlan(
        shot_id="shot_01",
        shot_number=1,
        scene_id="scene_01",
        start_time=0.0,
        end_time=6.0,
        duration_seconds=6.0,
        purpose="Intro hero shot",
        subject="Model",
        action="Walks forward",
        source_actions=["walks"],
    )

    scene = ScenePlan(
        scene_id="scene_01",
        scene_number=1,
        title="Opening",
        purpose="Hero",
        narrative_role=NarrativeRole.ESTABLISHING,
        start_time=0.0,
        end_time=6.0,
        duration_seconds=6.0,
        shots=[shot],
    )

    master_plan = MasterScenePlan(
        project_id="test-numeric",
        scenes=[scene],
        total_duration=6.0,
    )

    # Prompt with forbidden numeric parameters
    prompt = GeneratedPrompt(
        prompt_id="prompt_01",
        scene_id="scene_01",
        shot_id="shot_01",
        sequence_number=1,
        duration_seconds=6.0,
        prompt_text="Shot on 35mm lens at f/1.8 with ISO 800 and shutter speed 1/50s.",
        negative_constraints="distortion",
        source_actions=["walks"],
    )

    prompt_set = PromptSet(
        project_id="test-numeric",
        prompts=[prompt],
    )

    validated = validate_prompt_set(spec, master_plan, prompt_set, target_tool="Veo")
    camera_issues = [issue for issue in validated.validation_issues if issue.issue_type == "UNSUPPORTED_CAMERA_PARAMETER"]
    assert len(camera_issues) > 0
    assert validated.status == PromptStatus.BLOCKED
