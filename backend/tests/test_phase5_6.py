import pytest
from app.schemas.agent import Gap, Question, Answer, Importance, GapStatus, QuestionStatus, AnswerType, QuestionGenerationResult, GapCategory
from app.graph.nodes.ask_questions import ask_questions
from app.graph.nodes.update_state import update_state
from app.graph.nodes.re_analyze import re_analyze
from app.graph.routing import route_after_gap_detection
from unittest.mock import patch, MagicMock

@pytest.fixture
def base_state():
    return {
        "gaps": [
            Gap(
                id="g1",
                category=GapCategory.CHARACTER,
                importance=Importance.CRITICAL,
                description="Age missing",
                evidence="No age",
                status=GapStatus.OPEN
            ),
            Gap(
                id="g2",
                category=GapCategory.LOCATION,
                importance=Importance.IMPORTANT,
                description="Lighting missing",
                evidence="No lighting",
                status=GapStatus.OPEN
            ),
            Gap(
                id="g3",
                category=GapCategory.AUDIO,
                importance=Importance.OPTIONAL,
                description="Music genre missing",
                evidence="No genre",
                status=GapStatus.OPEN
            )
        ],
        "questions": [],
        "answers": [],
        "current_round": 0,
        "max_rounds": 2,
        "original_script": "A character walks in a room.",
        "analysis": {}
    }

@patch('app.graph.nodes.ask_questions.LLMService')
def test_ask_questions_filters_gaps(mock_llm, base_state):
    # Setup mock to return a valid QuestionGenerationResult
    mock_instance = MagicMock()
    mock_llm.return_value = mock_instance
    mock_instance.generate_structured.return_value = QuestionGenerationResult(
        questions=[
            Question(
                id="q_new1",
                gap_ids=["g1", "g2"],
                question="What is the age and lighting?",
                category="COMBINED",
                priority=Importance.CRITICAL
            )
        ]
    )
    
    new_state = ask_questions(base_state)
    
    assert len(new_state["questions"]) == 1
    assert new_state["questions"][0].status == QuestionStatus.PENDING
    assert new_state["status"] == "WAITING_FOR_USER"
    
    # Check that LLM was called
    assert mock_instance.generate_structured.called
    
    # Check that optional gap was NOT included in the prompt
    call_args = mock_instance.generate_structured.call_args[0][0]
    assert "g1" in call_args
    assert "g2" in call_args
    assert "g3" not in call_args

def test_update_state_processes_answers(base_state):
    q1 = Question(
        id="q1",
        gap_ids=["g1"],
        question="Age?",
        category="CHARACTER",
        priority=Importance.CRITICAL,
        status=QuestionStatus.PENDING
    )
    
    base_state["questions"] = [q1]
    base_state["new_answers"] = [
        Answer(question_id="q1", answer="30 years old", answer_type=AnswerType.TEXT)
    ]
    base_state["status"] = "WAITING_FOR_USER"
    
    new_state = update_state(base_state)
    
    assert new_state["questions"][0].status == QuestionStatus.ANSWERED
    assert new_state["questions"][0].answer == "30 years old"
    assert len(new_state["answers"]) == 1
    assert new_state["answers"][0].answer == "30 years old"
    assert new_state["current_round"] == 1
    assert new_state["status"] == "ANALYZING"

@patch('app.graph.nodes.re_analyze.LLMService')
def test_re_analyze_updates_gaps(mock_llm, base_state):
    mock_instance = MagicMock()
    mock_llm.return_value = mock_instance
    
    # Mock the LLM to return the first gap as RESOLVED
    g1_resolved = Gap(**base_state["gaps"][0].model_dump())
    g1_resolved.status = GapStatus.RESOLVED
    
    base_state["answers"] = [
        Answer(question_id="q1", answer="30 years old", answer_type=AnswerType.TEXT)
    ]
    
    from app.schemas.agent import GapDetectionResult
    mock_instance.generate_structured.return_value = GapDetectionResult(
        gaps=[g1_resolved]  # LLM only returns the modified ones or we append missing
    )

    print("BEFORE RE_ANALYZE, MOCK RETURNS:", mock_instance.generate_structured.return_value.gaps[0].status)
    new_state = re_analyze(base_state)
    
    print("NEW STATE STATUS:", new_state.get("status"))
    print("NEW STATE ERROR:", new_state.get("error"))
    
    print("NEW STATE GAPS:", [g.model_dump() for g in new_state["gaps"]])
    
    assert len(new_state["gaps"]) >= 1
    # Find g1
    g1_new = next(g for g in new_state["gaps"] if g.id == "g1")
    assert g1_new.status == GapStatus.RESOLVED
    assert new_state["status"] == "ANALYZING"

def test_routing_respects_max_rounds(base_state):
    base_state["current_round"] = 2
    base_state["max_rounds"] = 2
    
    # Even if critical gaps are open
    assert route_after_gap_detection(base_state) == "PROCEED"

def test_routing_asks_if_critical_open(base_state):
    base_state["current_round"] = 0
    assert route_after_gap_detection(base_state) == "ASK_QUESTIONS"

def test_routing_proceeds_if_all_resolved(base_state):
    for g in base_state["gaps"]:
        g.status = GapStatus.RESOLVED
        
    assert route_after_gap_detection(base_state) == "PROCEED"

@patch('app.graph.nodes.ask_questions.LLMService')
def test_ask_questions_fallback_gap_ids(mock_llm, base_state):
    # Setup mock to return an invalid gap_id
    mock_instance = MagicMock()
    mock_llm.return_value = mock_instance
    mock_instance.generate_structured.return_value = QuestionGenerationResult(
        questions=[
            Question(
                id="q_new2",
                gap_ids=["invalid_string"],
                question="What is this?",
                category="COMBINED",
                priority=Importance.OPTIONAL
            )
        ]
    )
    
    new_state = ask_questions(base_state)
    
    # Question should be discarded, length remains 0
    assert len(new_state["questions"]) == 0
    assert new_state["status"] == "ANALYZING"

@patch('app.graph.nodes.ask_questions.LLMService')
def test_ask_questions_zero_questions(mock_llm, base_state):
    # Setup mock to return 0 questions
    mock_instance = MagicMock()
    mock_llm.return_value = mock_instance
    mock_instance.generate_structured.return_value = QuestionGenerationResult(
        questions=[]
    )
    
    new_state = ask_questions(base_state)
    
    assert len(new_state["questions"]) == 0
    assert new_state["status"] == "ANALYZING"

def test_route_after_ask_questions():
    from app.graph.routing import route_after_ask_questions
    # No questions
    assert route_after_ask_questions({"questions": []}) == "PROCEED"
    
    # Only answered questions
    q1 = Question(id="1", question="?", category="X", priority=Importance.IMPORTANT, status=QuestionStatus.ANSWERED)
    assert route_after_ask_questions({"questions": [q1]}) == "PROCEED"
    
    # Pending questions
    q2 = Question(id="2", question="?", category="X", priority=Importance.IMPORTANT, status=QuestionStatus.PENDING)
    assert route_after_ask_questions({"questions": [q1, q2]}) == "WAIT_FOR_ANSWERS"

