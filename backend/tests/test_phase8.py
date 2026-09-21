import pytest
from unittest.mock import patch, MagicMock
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.specification import (
    VideoSpecification, OutputRequirements, ActionSpec, CharacterSpec, ProductSpec, LocationSpec
)
from app.schemas.scene_plan import MasterScenePlan, ScenePlan, ShotPlan, NarrativeRole, PlanStatus
from app.graph.nodes.scene_planner import scene_planner, validate_scene_plan
from app.graph.graph import build_graph

def test_duration_validation():
    """Test 39 & 44: Timing validator detects duration mismatch."""
    spec = VideoSpecification(
        project_id="test",
        output_requirements=OutputRequirements(duration_seconds=10)
    )
    
    # Valid plan
    plan = MasterScenePlan(
        scenes=[
            ScenePlan(
                scene_id="s1", scene_number=1, title="Intro", purpose="Start", narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0, end_time=10, duration_seconds=10,
                shots=[
                    ShotPlan(
                        shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=10, duration_seconds=10, purpose="Establish", subject="Woman", action="Enters"
                    )
                ]
            )
        ]
    )
    
    validated = validate_scene_plan(spec, plan)
    assert validated.status == PlanStatus.READY
    
    # Invalid plan: scene duration sum != target
    bad_plan = MasterScenePlan(
        scenes=[
            ScenePlan(
                scene_id="s1", scene_number=1, title="Intro", purpose="Start", narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0, end_time=8, duration_seconds=8,
                shots=[
                    ShotPlan(
                        shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=8, duration_seconds=8, purpose="Establish", subject="Woman", action="Enters"
                    )
                ]
            )
        ]
    )
    validated_bad = validate_scene_plan(spec, bad_plan)
    assert validated_bad.status == PlanStatus.BLOCKED
    assert any(iss.issue_type == "DURATION_MISMATCH" for iss in validated_bad.validation_issues)

def test_action_coverage():
    """Test 38 & 43: Action coverage ensures no required actions are skipped."""
    spec = VideoSpecification(
        project_id="test",
        output_requirements=OutputRequirements(duration_seconds=10),
        actions=[
            ActionSpec(id="act1", action="Walks in", required=True),
            ActionSpec(id="act2", action="Picks up product", required=True)
        ]
    )
    
    # Plan missing act2
    plan = MasterScenePlan(
        scenes=[
            ScenePlan(
                scene_id="s1", scene_number=1, title="Intro", purpose="Start", narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0, end_time=10, duration_seconds=10,
                shots=[
                    ShotPlan(
                        shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=10, duration_seconds=10, purpose="Establish", subject="Woman", action="Enters",
                        source_actions=["act1"]
                    )
                ]
            )
        ]
    )
    
    validated = validate_scene_plan(spec, plan)
    assert validated.status == PlanStatus.BLOCKED
    assert any(iss.issue_type == "MISSING_ACTIONS" for iss in validated.validation_issues)
    
def test_continuity_reference_validation():
    """Test 40 & 45: Continuity checks for valid entity references."""
    spec = VideoSpecification(
        project_id="test",
        output_requirements=OutputRequirements(duration_seconds=5),
        characters=[CharacterSpec(id="char1", name="Woman")]
    )
    
    plan = MasterScenePlan(
        scenes=[
            ScenePlan(
                scene_id="s1", scene_number=1, title="Intro", purpose="Start", narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0, end_time=5, duration_seconds=5,
                character_ids=["char999"], # invalid character reference
                shots=[
                    ShotPlan(
                        shot_id="shot1", shot_number=1, scene_id="s1", start_time=0, end_time=5, duration_seconds=5, purpose="Establish", subject="Woman", action="Enters"
                    )
                ]
            )
        ]
    )
    
    validated = validate_scene_plan(spec, plan)
    assert any(iss.issue_type == "INVALID_CHARACTER" for iss in validated.validation_issues)
    # Important severity isn't strictly blocking by default, but validation issue is created

def test_hallucination_prevention_prompt():
    """Test 41: Hallucination prevention prompt inclusion."""
    from app.prompts.scene_planner import SCENE_PLANNER_PROMPT
    assert "DO NOT invent technical camera parameters" in SCENE_PLANNER_PROMPT

@patch('app.graph.nodes.detect_gaps.LLMService')
@patch('app.graph.nodes.analyze_script.LLMService')
@patch('app.graph.nodes.build_video_spec.LLMService')
@patch('app.graph.nodes.scene_planner.LLMService')
def test_graph_integration_phase8(mock_planner, mock_build, mock_analyze, mock_detect):
    """Test 35: LangGraph integration up to scene_planner."""
    from app.schemas.script import ScriptAnalysis
    from app.schemas.agent import GapDetectionResult
    
    mock_analyze.return_value.generate_structured.return_value = ScriptAnalysis()
    mock_detect.return_value.generate_structured.return_value = GapDetectionResult(gaps=[])
    
    mock_spec = VideoSpecification(project_id="test-1", output_requirements=OutputRequirements(duration_seconds=5))
    mock_build.return_value.generate_structured.return_value = mock_spec
    
    # Return a completely valid plan matching 5s
    mock_plan = MasterScenePlan(
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

    graph = build_graph()
    initial_state = {"project_id": "test-1", "original_script": "text"}
    config = {"configurable": {"thread_id": "test-phase8"}}
    
    final_state = graph.invoke(initial_state, config)
    
    assert final_state["status"] == AgentStatus.VALIDATING
    assert final_state["scene_plan"] is not None
    assert final_state["scene_plan"].status == PlanStatus.READY
