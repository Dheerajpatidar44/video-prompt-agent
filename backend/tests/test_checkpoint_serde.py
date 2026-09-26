# tests/test_checkpoint_serde.py
import asyncio
import logging
from unittest.mock import AsyncMock, patch

from app.graph.graph import build_graph
from app.schemas.script import InitialAnalysisResult
from app.schemas.agent import Gap, GapCategory, Importance, GapStatus, Question, AnswerType, QuestionStatus

logging.basicConfig(level=logging.WARNING)


async def _run():
    graph = build_graph()
    config = {"configurable": {"thread_id": "serde-real-execution-test"}}

    fake_gap = Gap(
        id="gap-1",
        category=GapCategory.LOCATION,
        importance=Importance.CRITICAL,
        title="Test gap",
        description="A test gap for serde verification",
        evidence="test evidence",
        status=GapStatus.OPEN,
    )
    fake_question = Question(
        id="q-1",
        gap_ids=["gap-1"],
        question="Where does this take place?",
        category="LOCATION",
        priority=Importance.CRITICAL,
        answer_type=AnswerType.TEXT,
        status=QuestionStatus.PENDING,
    )
    fake_analysis = InitialAnalysisResult(gaps=[fake_gap], questions=[fake_question])

    # Patch the SHARED llm_service singleton — every node imports this same
    # object, so this one patch covers analyze_script.py's call. No real
    # network/API call happens; this returns instantly.
    from app.llm.claude_client import llm_service
    with patch.object(llm_service, "generate_structured", new=AsyncMock(return_value=fake_analysis)):
        initial_state = {
            "project_id": "serde-test-doc",
            "original_script": "A test script for serde verification.",
            "script_source": "txt",
        }
        # Our fake analysis has an unresolved CRITICAL gap + a question, so
        # route_after_analysis sends this to WAIT_FOR_ANSWERS — the graph
        # pauses at interrupt_before=["update_state"]. This means ONLY
        # analyze_script gets called; build_video_spec, re_analyze, and
        # generate are never reached, so nothing else needs mocking.
        await graph.ainvoke(initial_state, config)

    snapshot = graph.get_state(config)
    loaded_gaps = snapshot.values.get("gaps", [])
    loaded_questions = snapshot.values.get("questions", [])

    assert len(loaded_gaps) == 1, "Gap did not round-trip through real graph execution"
    assert isinstance(loaded_gaps[0], Gap), f"Expected Gap instance, got {type(loaded_gaps[0])}"
    assert len(loaded_questions) == 1, "Question did not round-trip"
    assert isinstance(loaded_questions[0], Question), f"Expected Question instance, got {type(loaded_questions[0])}"

    print("✅ Real graph execution round-tripped through the actual checkpointer — types preserved correctly.")


def test_checkpoint_roundtrip_via_real_execution():
    asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(_run())