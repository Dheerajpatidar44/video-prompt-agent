import pytest
from app.graph.state import AgentState
from app.schemas.agent import Gap, Question, Importance, AgentStatus, GapStatus, QuestionStatus
from app.graph.routing import route_after_gap_detection
from app.graph.graph import build_graph
from app.graph.nodes.initialize_state import initialize_state
from app.graph.nodes.update_state import update_state

def test_initial_state_and_defaults():
    # 1. Initial state can be created.
    # 2. State defaults are correct.
    initial: AgentState = {"project_id": "proj-1"}
    state = initialize_state(initial)
    
    assert state["current_round"] == 0
    assert state["max_rounds"] == 2
    assert state["gaps"] == []
    assert state["status"] == AgentStatus.ANALYZING

def test_round_counter_works():
    # 3. Round counter works.
    from app.schemas.agent import Answer, AnswerType
    state: AgentState = {"current_round": 0, "new_answers": [Answer(question_id="q1", answer="test", answer_type=AnswerType.TEXT)]}
    new_state = update_state(state)
    assert new_state["current_round"] == 1

def test_gap_and_question_models():
    # 5. Gap model validates correctly.
    gap = Gap(
        id="g1",
        category="CHARACTER",
        description="Missing main character age",
        importance=Importance.CRITICAL,
        evidence="Script says 'A woman' without age."
    )
    assert gap.id == "g1"
    assert gap.status == GapStatus.OPEN
    
    # 6. Question model validates correctly.
    question = Question(
        id="q1",
        gap_ids=["g1"],
        question="What is the age of the main character?",
        category="CHARACTER",
        priority=Importance.CRITICAL
    )
    assert question.id == "q1"
    assert question.status == QuestionStatus.PENDING

def test_routing_ask_questions():
    # 7. Routing returns ASK_QUESTIONS only when CRITICAL gap exists AND current_round < max_rounds.
    state: AgentState = {
        "current_round": 0,
        "max_rounds": 2,
        "gaps": [
            Gap(
                id="g1", category="CHARACTER", description="desc",
                importance=Importance.CRITICAL, evidence="evidence", status=GapStatus.OPEN
            )
        ]
    }
    route = route_after_gap_detection(state)
    assert route == "ASK_QUESTIONS"

def test_routing_proceed_when_only_optional():
    state: AgentState = {
        "current_round": 0,
        "max_rounds": 2,
        "gaps": [
            Gap(
                id="g1", category="CHARACTER", description="desc",
                importance=Importance.OPTIONAL, evidence="evidence", status=GapStatus.OPEN
            )
        ]
    }
    route = route_after_gap_detection(state)
    assert route == "PROCEED"

def test_routing_respects_max_rounds():
    # 4. Maximum rounds are respected.
    # 8. Routing function returns PROCEED once current_round reaches max_rounds, even if CRITICAL gaps still remain.
    state: AgentState = {
        "current_round": 2,
        "max_rounds": 2,
        "gaps": [
            Gap(
                id="g1", category="CHARACTER", description="desc",
                importance=Importance.CRITICAL, evidence="evidence", status=GapStatus.OPEN
            )
        ]
    }
    route = route_after_gap_detection(state)
    assert route == "PROCEED"

from unittest.mock import patch, MagicMock

@patch('app.graph.nodes.detect_gaps.LLMService')
@patch('app.graph.nodes.analyze_script.LLMService')
@patch('app.graph.nodes.build_video_spec.LLMService')
@patch('app.graph.nodes.scene_planner.LLMService')
def test_graph_compiles_and_executes(mock_planner, mock_build, mock_analyze, mock_detect):
    # 9. Graph can compile successfully.
    # 10. Placeholder graph can execute without Ollama.
    # 11. No external LLM API is required.
    
    # Mock return values for LLMs
    from app.schemas.script import ScriptAnalysis
    from app.schemas.agent import GapDetectionResult
    from app.schemas.specification import VideoSpecification
    from app.schemas.scene_plan import MasterScenePlan
    
    mock_analyze.return_value.generate_structured.return_value = ScriptAnalysis()
    mock_detect.return_value.generate_structured.return_value = GapDetectionResult()
    mock_build.return_value.generate_structured.return_value = VideoSpecification(project_id="test-1")
    mock_planner.return_value.generate_structured.return_value = MasterScenePlan()

    graph = build_graph()
    
    initial_state = {"project_id": "test-1"}
    
    # We run it up to the interrupt point (update_state) if it were to ask questions,
    # but initially gaps are empty, so it should route to build_video_spec and finish.
    config = {"configurable": {"thread_id": "1"}}
    final_state = graph.invoke(initial_state, config)
    
    assert final_state["status"] == AgentStatus.VALIDATING
