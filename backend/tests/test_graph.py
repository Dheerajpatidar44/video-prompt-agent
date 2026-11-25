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
    
    initial_state = {
        "project_id": "test-1",
        "original_script": "A woman drinks coffee in a cafe.",
    }
    
    # We run it up to the interrupt point (update_state) if it were to ask questions,
    # but initially gaps are empty, so it should route to build_video_spec and finish.
    config = {"configurable": {"thread_id": "1"}}
    final_state = await graph.ainvoke(initial_state, config)
    
    # Phase 1 ends after prompts + keyframe images are ready for user review
    assert final_state["status"] == AgentStatus.PROMPTS_READY


def test_update_state_processes_answers():
    from app.schemas.agent import Answer, AnswerType, GapCategory
    q1 = Question(
        id="q1",
        gap_ids=["g1"],
        question="Age?",
        category="CHARACTER",
        priority=Importance.CRITICAL,
        status=QuestionStatus.PENDING,
    )
    state: AgentState = {
        "questions": [q1],
        "new_answers": [Answer(question_id="q1", answer="30 years old", answer_type=AnswerType.TEXT)],
        "answers": [],
        "current_round": 0,
        "status": AgentStatus.WAITING_FOR_USER,
    }
    new_state = update_state(state)
    assert new_state["questions"][0].status == QuestionStatus.ANSWERED
    assert new_state["questions"][0].answer == "30 years old"
    assert len(new_state["answers"]) == 1
    assert new_state["answers"][0].answer == "30 years old"
    assert new_state["current_round"] == 1
    assert new_state["status"] == "ANALYZING"


@patch('app.graph.nodes.re_analyze.llm_service')
@pytest.mark.asyncio
async def test_re_analyze_updates_gaps_and_asks_questions(mock_llm):
    from app.schemas.agent import GapCategory, ReAnalysisResult, Answer, AnswerType
    from app.graph.nodes.re_analyze import re_analyze

    g1 = Gap(
        id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL,
        description="Age missing", evidence="No age", status=GapStatus.OPEN
    )
    g2 = Gap(
        id="g2", category=GapCategory.LOCATION, importance=Importance.IMPORTANT,
        description="Lighting missing", evidence="No lighting", status=GapStatus.OPEN
    )
    g1_resolved = Gap(
        id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL,
        description="Age missing", evidence="No age", status=GapStatus.RESOLVED
    )
    new_question = Question(
        id="q2", gap_ids=["g2"], question="What kind of lighting?",
        category="LOCATION", priority=Importance.IMPORTANT, status=QuestionStatus.PENDING
    )

    state: AgentState = {
        "gaps": [g1, g2],
        "questions": [],
        "answers": [Answer(question_id="q1", answer="30 years old", answer_type=AnswerType.TEXT)],
        "current_round": 0,
        "max_rounds": 2,
        "original_script": "A character walks in a room.",
        "analysis": {},
    }

    mock_llm.generate_structured = AsyncMock(return_value=ReAnalysisResult(
        gaps=[g1_resolved, g2],
        questions=[new_question],
    ))

    new_state = await re_analyze(state)
    assert len(new_state["gaps"]) == 2
    assert next(g for g in new_state["gaps"] if g.id == "g1").status == GapStatus.RESOLVED
    assert new_state["status"] == "WAITING_FOR_USER"
    assert len(new_state["questions"]) == 1
    assert new_state["questions"][0].id == "q2"


def test_routing_helpers():
    from app.graph.routing import has_unresolved_priority_gaps, within_round_limit
    from app.schemas.agent import GapCategory

    gaps = [
        Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL,
            description="Age missing", evidence="No age", status=GapStatus.OPEN)
    ]
    assert has_unresolved_priority_gaps(gaps) is True
    gaps[0].status = GapStatus.RESOLVED
    assert has_unresolved_priority_gaps(gaps) is False

    assert within_round_limit(0, 2) is True
    assert within_round_limit(1, 2) is True
    assert within_round_limit(2, 2) is False


@patch('app.graph.nodes.build_video_spec.llm_service')
@pytest.mark.asyncio
async def test_build_video_spec_ready_and_blocked(mock_llm):
    from app.graph.nodes.build_video_spec import build_video_spec
    from app.schemas.specification import VideoSpecification, SpecStatus
    from app.schemas.agent import GapCategory

    # Case 1: Ready
    mock_spec = VideoSpecification(project_id="proj-1", unresolved_items=[])
    mock_llm.generate_structured = AsyncMock(return_value=mock_spec)

    state: AgentState = {"project_id": "proj-1", "original_script": "A woman walks in.", "gaps": []}
    new_state = await build_video_spec(state)
    assert new_state["status"] == AgentStatus.GENERATING
    assert new_state["video_specification"].status == SpecStatus.READY

    # Case 2: Blocked by critical open gap
    state_blocked: AgentState = {
        "project_id": "proj-1",
        "gaps": [
            Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL,
                description="Age missing", evidence="missing", status=GapStatus.OPEN)
        ],
    }
    new_state_blocked = await build_video_spec(state_blocked)
    assert new_state_blocked["video_specification"].status == SpecStatus.BLOCKED

