import pytest
from app.graph.state import AgentState
from app.schemas.agent import Gap, Question, Importance, AgentStatus, GapStatus, QuestionStatus
from app.graph.routing import route_after_analysis
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
    # 7. Routing returns WAIT_FOR_ANSWERS only when status == WAITING_FOR_USER
    state: AgentState = {
        "status": AgentStatus.WAITING_FOR_USER
    }
    route = route_after_analysis(state)
    assert route == "WAIT_FOR_ANSWERS"

def test_routing_proceed_when_analyzing():
    state: AgentState = {
        "status": AgentStatus.ANALYZING
    }
    route = route_after_analysis(state)
    assert route == "PROCEED"


from unittest.mock import patch, AsyncMock
import pytest

@patch('app.graph.nodes.generate_scenes_and_prompts.llm_service')
@patch('app.graph.nodes.build_video_spec.llm_service')
@patch('app.graph.nodes.analyze_script.llm_service')
@pytest.mark.asyncio
async def test_graph_compiles_and_executes(mock_analyze, mock_build, mock_generate):
    # 9. Graph can compile successfully.
    # 10. Placeholder graph can execute without Ollama.
    # 11. No external LLM API is required.
    
    # Mock return values for LLMs
    from app.schemas.script import InitialAnalysisResult
    from app.schemas.specification import VideoSpecification
    from app.schemas.generation import GenerationResult, GeneratedScenePlan, GeneratedPromptItem, GeneratedShotPlan
    
    mock_analyze.generate_structured = AsyncMock(return_value=InitialAnalysisResult())
    mock_build.generate_structured = AsyncMock(return_value=VideoSpecification(project_id="test-1"))
    mock_generate.generate_structured = AsyncMock(return_value=GenerationResult(
        scenes=[
            GeneratedScenePlan(
                scene_id="s1", scene_number=1, title="title", purpose="purpose",
                narrative_role="ACTION", start_time=0.0, end_time=1.0, duration_seconds=1.0,
                location_id="loc", character_ids=[], product_ids=[],
                shots=[GeneratedShotPlan(
                    shot_id="shot1", shot_number=1, scene_id="s1", start_time=0.0, end_time=1.0,
                    duration_seconds=1.0, purpose="purpose", subject="subject",
                    action="action", framing="framing", camera_movement="none", source_actions=[]
                )]
            )
        ],
        prompts=[
            GeneratedPromptItem(
                prompt_id="p1", scene_id="s1", shot_id="shot1", sequence_number=1,
                duration_seconds=1.0, prompt_text="A prompt", negative_constraints="",
                continuity_requirements=[], source_actions=[]
            )
        ]
    ))

    graph = build_graph()
    
    initial_state = {"project_id": "test-1"}
    
    # We run it up to the interrupt point (update_state) if it were to ask questions,
    # but initially gaps are empty, so it should route to build_video_spec and finish.
    config = {"configurable": {"thread_id": "1"}}
    final_state = await graph.ainvoke(initial_state, config)
    
    # Wait, the final status is now COMPLETED because we returned a valid prompt_set
    assert final_state["status"] == AgentStatus.COMPLETED
