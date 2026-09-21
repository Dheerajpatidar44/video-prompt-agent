import pytest
from unittest.mock import patch
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet, PromptStatus, ValidationIssue
from app.schemas.specification import VideoSpecification, OutputRequirements, ActionSpec, CharacterSpec, CameraSpec
from app.schemas.scene_plan import MasterScenePlan, ScenePlan, ShotPlan, NarrativeRole, PlanStatus
from app.validators.prompt_validation import validate_prompt_set
from app.prompts.prompt_generator import PROMPT_GENERATOR_INSTRUCTION
from app.graph.graph import build_graph
from app.schemas.agent import AgentStatus

# --- 1-2. Model Tests ---
def test_generated_prompt_model():
    p = GeneratedPrompt(
        prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1,
        duration_seconds=5.0, prompt_text="Test", source_actions=["act1"]
    )
    assert p.prompt_text == "Test"

def test_promptset_model():
    ps = PromptSet(total_duration=10.0, status=PromptStatus.READY)
    assert ps.total_duration == 10.0

# --- 4-7, 11-15. Validation Tests ---
def test_prompt_count_matches_shots():
    spec = VideoSpecification(project_id="test", output_requirements=OutputRequirements(duration_seconds=5))
    master = MasterScenePlan(
        total_duration=5,
        scenes=[ScenePlan(
            scene_id="s1", scene_number=1, title="Intro", purpose="A", narrative_role=NarrativeRole.ESTABLISHING,
            start_time=0, end_time=5, duration_seconds=5,
            shots=[
                ShotPlan(shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="A", subject="A", action="A"),
                ShotPlan(shot_id="shot2", shot_number=2, scene_id="s1", start_time=5, end_time=10, duration_seconds=5, purpose="A", subject="A", action="A")
            ]
        )]
    )
    
    ps = PromptSet(
        total_duration=5,
        prompts=[GeneratedPrompt(prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=5, prompt_text="Test")]
    )
    
    validated = validate_prompt_set(spec, master, ps)
    assert validated.status == PromptStatus.BLOCKED
    assert any(i.issue_type == "MISSING_PROMPT" for i in validated.validation_issues)

def test_duration_preserved():
    spec = VideoSpecification(project_id="test", output_requirements=OutputRequirements(duration_seconds=5))
    master = MasterScenePlan(
        total_duration=5,
        scenes=[ScenePlan(
            scene_id="s1", scene_number=1, title="Intro", purpose="A", narrative_role=NarrativeRole.ESTABLISHING,
            start_time=0, end_time=5, duration_seconds=5,
            shots=[ShotPlan(shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="A", subject="A", action="A")]
        )]
    )
    ps = PromptSet(
        total_duration=5,
        prompts=[GeneratedPrompt(prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=4, prompt_text="Test")]
    )
    validated = validate_prompt_set(spec, master, ps)
    assert any(i.issue_type == "DURATION_MISMATCH" for i in validated.validation_issues)

def test_action_traceability():
    spec = VideoSpecification(project_id="test", output_requirements=OutputRequirements(duration_seconds=5))
    master = MasterScenePlan(
        total_duration=5,
        scenes=[ScenePlan(
            scene_id="s1", scene_number=1, title="Intro", purpose="A", narrative_role=NarrativeRole.ESTABLISHING,
            start_time=0, end_time=5, duration_seconds=5,
            shots=[ShotPlan(shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="A", subject="A", action="A", source_actions=["act1"])]
        )]
    )
    ps = PromptSet(
        total_duration=5,
        prompts=[GeneratedPrompt(prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=5, prompt_text="Test", source_actions=[])]
    )
    validated = validate_prompt_set(spec, master, ps)
    assert any(i.issue_type == "MISSING_SOURCE_ACTIONS" for i in validated.validation_issues)

def test_hallucination_prompt_rules():
    assert "DO NOT invent technical camera parameters" in PROMPT_GENERATOR_INSTRUCTION

def test_unsupported_camera_parameter_detection():
    spec = VideoSpecification(project_id="test", output_requirements=OutputRequirements(duration_seconds=5))
    master = MasterScenePlan(
        total_duration=5,
        scenes=[ScenePlan(
            scene_id="s1", scene_number=1, title="Intro", purpose="A", narrative_role=NarrativeRole.ESTABLISHING,
            start_time=0, end_time=5, duration_seconds=5,
            shots=[ShotPlan(shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="A", subject="A", action="A")]
        )]
    )
    ps = PromptSet(
        total_duration=5,
        prompts=[GeneratedPrompt(prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=5, prompt_text="A beautiful shot with ISO 800 and 85mm lens")]
    )
    validated = validate_prompt_set(spec, master, ps)
    assert any(i.issue_type == "UNSUPPORTED_CAMERA_PARAMETER" for i in validated.validation_issues)

def test_supported_camera_parameter_detection():
    # If spec has it, it shouldn't flag it as hallucinated
    spec = VideoSpecification(
        project_id="test", 
        output_requirements=OutputRequirements(duration_seconds=5),
        camera=CameraSpec(camera_style="85mm lens at ISO 800")
    )
    master = MasterScenePlan(
        total_duration=5,
        scenes=[ScenePlan(
            scene_id="s1", scene_number=1, title="Intro", purpose="A", narrative_role=NarrativeRole.ESTABLISHING,
            start_time=0, end_time=5, duration_seconds=5,
            shots=[ShotPlan(shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="A", subject="A", action="A")]
        )]
    )
    ps = PromptSet(
        total_duration=5,
        prompts=[GeneratedPrompt(prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=5, prompt_text="A beautiful shot with ISO 800 and 85mm lens")]
    )
    validated = validate_prompt_set(spec, master, ps)
    assert not any(i.issue_type == "UNSUPPORTED_CAMERA_PARAMETER" for i in validated.validation_issues)

def test_scene_plan_blocked_prevents_generation():
    spec = VideoSpecification(project_id="test", output_requirements=OutputRequirements(duration_seconds=5))
    master = MasterScenePlan(total_duration=5, status=PlanStatus.BLOCKED)
    ps = PromptSet()
    validated = validate_prompt_set(spec, master, ps)
    assert validated.status == PromptStatus.BLOCKED
    assert any(i.issue_type == "SCENE_PLAN_BLOCKED" for i in validated.validation_issues)

@patch('app.graph.nodes.detect_gaps.LLMService')
@patch('app.graph.nodes.analyze_script.LLMService')
@patch('app.graph.nodes.build_video_spec.LLMService')
@patch('app.graph.nodes.scene_planner.LLMService')
@patch('app.graph.nodes.prompt_generator.LLMService')
def test_graph_integration_phase9(mock_prompt, mock_planner, mock_build, mock_analyze, mock_detect):
    from app.schemas.script import ScriptAnalysis
    from app.schemas.agent import GapDetectionResult
    
    mock_analyze.return_value.generate_structured.return_value = ScriptAnalysis()
    mock_detect.return_value.generate_structured.return_value = GapDetectionResult(gaps=[])
    
    mock_spec = VideoSpecification(project_id="test-1", output_requirements=OutputRequirements(duration_seconds=5))
    mock_build.return_value.generate_structured.return_value = mock_spec
    
    mock_plan = MasterScenePlan(
        total_duration=5,
        status=PlanStatus.READY,
        scenes=[
            ScenePlan(
                scene_id="s1", scene_number=1, title="Intro", purpose="Start", narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0, end_time=5, duration_seconds=5,
                shots=[
                    ShotPlan(
                        shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="Establish", subject="Woman", action="Enters"
                    )
                ]
            )
        ]
    )
    mock_planner.return_value.generate_structured.return_value = mock_plan

    # Mock the generated prompt
    mock_prompt.return_value.generate_structured.return_value = GeneratedPrompt(
        prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1, duration_seconds=5, prompt_text="Test prompt", source_actions=[]
    )

    graph = build_graph()
    initial_state = {"project_id": "test-1", "original_script": "text"}
    config = {"configurable": {"thread_id": "test-phase9"}}
    
    final_state = graph.invoke(initial_state, config)
    
    assert final_state["status"] == AgentStatus.VALIDATING
    assert final_state["prompt_set"] is not None
    assert final_state["prompt_set"].status == PromptStatus.READY
    assert len(final_state["prompt_set"].prompts) == 1

def test_api_get_prompts():
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    # The actual testing of this endpoint via API will fail if no graph memory is there for the specific thread ID, 
    # but we can test the 404 path cleanly without Ollama.
    response = client.get("/api/v1/scripts/unknown_thread/prompts")
    assert response.status_code == 404
