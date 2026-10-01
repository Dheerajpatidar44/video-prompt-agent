import pytest
from app.schemas.agent import Gap, Question, Answer, Importance, GapStatus, QuestionStatus, AnswerType, GapCategory, ReAnalysisResult
from app.graph.nodes.update_state import update_state
from app.graph.nodes.re_analyze import re_analyze
from app.graph.routing import route_after_analysis, has_unresolved_priority_gaps, within_round_limit
from unittest.mock import patch, AsyncMock

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


@patch('app.graph.nodes.re_analyze.llm_service')
@pytest.mark.asyncio
async def test_re_analyze_updates_gaps_and_asks_questions(mock_llm, base_state):
    # Mock LLM to return g1 resolved, but g2 still open with a new question
    g1_resolved = Gap(**base_state["gaps"][0].model_dump())
    g1_resolved.status = GapStatus.RESOLVED
    
    g2_open = Gap(**base_state["gaps"][1].model_dump())
    g2_open.status = GapStatus.OPEN
    
    new_question = Question(
        id="q2",
        gap_ids=["g2"],
        question="What kind of lighting?",
        category="LOCATION",
        priority=Importance.IMPORTANT,
        status=QuestionStatus.PENDING
    )
    
    base_state["answers"] = [
        Answer(question_id="q1", answer="30 years old", answer_type=AnswerType.TEXT)
    ]
    base_state["current_round"] = 0
    
    mock_llm.generate_structured = AsyncMock(return_value=ReAnalysisResult(
        gaps=[g1_resolved, g2_open],
        questions=[new_question]
    ))

    new_state = await re_analyze(base_state)
    
    # We should have 3 gaps total (g3 was kept because the LLM didn't return it)
    assert len(new_state["gaps"]) == 3
    
    g1_new = next(g for g in new_state["gaps"] if g.id == "g1")
    assert g1_new.status == GapStatus.RESOLVED
    
    # Because there are unresolved priority gaps and a new question, status should be WAITING_FOR_USER
    assert new_state["status"] == "WAITING_FOR_USER"
    
    # Question should be added and round number set to current_round + 1
    assert len(new_state["questions"]) == 1
    assert new_state["questions"][0].id == "q2"
    assert new_state["questions"][0].round_number == 1

def test_has_unresolved_priority_gaps(base_state):
    assert has_unresolved_priority_gaps(base_state["gaps"]) is True
    
    for g in base_state["gaps"]:
        g.status = GapStatus.RESOLVED
    assert has_unresolved_priority_gaps(base_state["gaps"]) is False

def test_within_round_limit():
    assert within_round_limit(0, 2) is True
    assert within_round_limit(1, 2) is True
    assert within_round_limit(2, 2) is False

def test_route_after_analysis():
    assert route_after_analysis({"status": "WAITING_FOR_USER"}) == "WAIT_FOR_ANSWERS"
    assert route_after_analysis({"status": "ANALYZING"}) == "PROCEED"
    assert route_after_analysis({}) == "PROCEED"
