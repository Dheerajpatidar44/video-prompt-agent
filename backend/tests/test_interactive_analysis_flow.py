"""Comprehensive unit & integration tests for:
1. Strict schema compatibility with Vertex AI / Gemini (InitialAnalysisResult, ReAnalysisResult, Gap, Question)
2. LangGraph routing (WAIT_FOR_ANSWERS, STOP_ON_ERROR, PROCEED)
3. Interactive multi-turn Q&A flow:
   - Script analysis & gap detection
   - Questions generated and state pauses at WAITING_FOR_USER
   - User answers questions
   - Re-analysis evaluates gaps and triggers Round 2 if critical gaps remain
   - Gaps resolved -> proceeds to build_video_spec
   - Error in analysis -> halts at END, never proceeds to build_video_spec
"""
import pytest
from unittest.mock import AsyncMock, patch
from langgraph.checkpoint.memory import MemorySaver

from app.schemas.agent import (
    Gap,
    GapCategory,
    Importance,
    GapStatus,
    Question,
    QuestionStatus,
    AnswerType,
    Answer,
    AgentStatus,
    ReAnalysisResult,
)
from app.schemas.script import (
    InitialAnalysisResult,
    CharacterAnalysisItem,
    LocationAnalysisItem,
    ProductAnalysisItem,
    ActionAnalysisItem,
    TimingAnalysis,
)
from app.graph.routing import route_after_analysis
from app.graph.graph import build_graph, serde


# ======================================================================
# 1. Schema Compatibility & Strict Typing Tests
# ======================================================================

def test_initial_analysis_schema_has_no_untyped_fields():
    """Verify that InitialAnalysisResult JSON schema has explicit types on all properties."""
    schema = InitialAnalysisResult.model_json_schema()
    props = schema.get("properties", {})
    defs = schema.get("$defs", {})

    # Check key fields have types
    assert props["characters"]["type"] == "array"
    assert props["locations"]["type"] == "array"
    assert props["products"]["type"] == "array"
    assert props["actions"]["type"] == "array"
    assert props["gaps"]["type"] == "array"
    assert props["questions"]["type"] == "array"

    # Verify CharacterAnalysisItem definition has string types
    char_def = defs.get("CharacterAnalysisItem", {})
    assert char_def.get("properties", {}).get("name", {}).get("type") == "string"
    assert char_def.get("properties", {}).get("description", {}).get("type") == "string"


def test_gap_current_value_coercion_and_str_type():
    """Verify Gap.current_value is strictly typed as string and coerces primitives cleanly."""
    schema = Gap.model_json_schema()
    current_val_prop = schema.get("properties", {}).get("current_value", {})
    
    # Check that OpenAPI type is string (or anyOf with null/string, never raw object or untyped)
    val_types = [current_val_prop.get("type")]
    if "anyOf" in current_val_prop:
        val_types = [opt.get("type") for opt in current_val_prop["anyOf"]]
    assert "string" in val_types or val_types == ["string"]

    # Test coercion from int, float, bool, str
    g1 = Gap(
        id="gap-1", category=GapCategory.TIMING, importance=Importance.CRITICAL,
        title="Duration gap", description="Missing duration", evidence="none",
        current_value=10
    )
    assert g1.current_value == "10"

    g2 = Gap(
        id="gap-2", category=GapCategory.CHARACTER, importance=Importance.IMPORTANT,
        title="Hair color", description="Missing hair color", evidence="none",
        current_value="blonde"
    )
    assert g2.current_value == "blonde"

    g3 = Gap(
        id="gap-3", category=GapCategory.PRODUCT, importance=Importance.OPTIONAL,
        title="Logo present", description="Is logo on bottle?", evidence="none",
        current_value=True
    )
    assert g3.current_value == "True"

    g4 = Gap(
        id="gap-4", category=GapCategory.OTHER, importance=Importance.OPTIONAL,
        title="Empty", description="Empty", evidence="none",
        current_value=None
    )
    assert g4.current_value is None


def test_initial_analysis_instantiation_with_dicts_or_submodels():
    """Verify backward compatibility: InitialAnalysisResult accepts both raw dicts and typed submodels."""
    # Instantiation with dicts
    res1 = InitialAnalysisResult(
        story_objective="Promote luxury watch",
        characters=[{"name": "Elena", "description": "Elegant businesswoman"}],
        locations=[{"name": "Rooftop lounge", "description": "Overlooking city skyline"}],
        products=[{"name": "Chronograph", "description": "Rose gold casing"}],
        actions=[{"description": "Checks the time"}],
        timing={"pacing": "slow", "estimated_duration_seconds": 15.0},
    )
    assert len(res1.characters) == 1
    assert isinstance(res1.characters[0], CharacterAnalysisItem)
    assert res1.characters[0].name == "Elena"
    assert isinstance(res1.timing, TimingAnalysis)
    assert res1.timing.pacing == "slow"

    # model_dump produces clean dicts for downstream nodes
    dumped = res1.model_dump(exclude={"gaps", "questions"})
    assert dumped["characters"][0]["name"] == "Elena"
    assert dumped["timing"]["estimated_duration_seconds"] == 15.0


# ======================================================================
# 2. Routing Logic & Failure Guard Tests
# ======================================================================

def test_route_after_analysis_waiting_for_user():
    """When status is WAITING_FOR_USER, route to WAIT_FOR_ANSWERS."""
    state = {"status": AgentStatus.WAITING_FOR_USER, "questions": ["dummy"]}
    route = route_after_analysis(state)
    assert route == "WAIT_FOR_ANSWERS"


def test_route_after_analysis_error_halts_and_never_proceeds():
    """When an error occurred, route to STOP_ON_ERROR (never PROCEED to build spec)."""
    # Case A: status is ERROR
    state_err = {"status": AgentStatus.ERROR, "error": "Vertex AI 400 Bad Request"}
    assert route_after_analysis(state_err) == "STOP_ON_ERROR"

    # Case B: error string is present even if status was not updated
    state_err_str = {"status": AgentStatus.ANALYZING, "error": "Schema validation failed"}
    assert route_after_analysis(state_err_str) == "STOP_ON_ERROR"


def test_route_after_analysis_proceed_when_no_questions_and_no_errors():
    """When analysis completes with no open questions/gaps and no errors, route to PROCEED."""
    state_clean = {"status": AgentStatus.ANALYZING, "error": None}
    assert route_after_analysis(state_clean) == "PROCEED"


# ======================================================================
# 3. Interactive Multi-Turn Flow Integration Tests
# ======================================================================

@pytest.mark.asyncio
async def test_full_interactive_flow_with_q_and_a_pause():
    """Verify that when questions are generated, the graph PAUSES at update_state,

    waits for answers, re-analyzes, and then builds specification.
    """
    memory = MemorySaver(serde=serde)
    graph = build_graph(memory)
    config = {"configurable": {"thread_id": "test-interactive-session-001"}}

    # Mock Initial Analysis output with 1 critical gap & 1 question
    mock_gap = Gap(
        id="gap-dur-1",
        category=GapCategory.OUTPUT_REQUIREMENT,
        importance=Importance.CRITICAL,
        title="Unknown Duration",
        description="The target video duration was not specified in the script.",
        evidence="Script has no duration hint",
        status=GapStatus.OPEN,
    )
    mock_question = Question(
        id="q-dur-1",
        gap_ids=["gap-dur-1"],
        question="What is the desired duration of this commercial?",
        category="OUTPUT_REQUIREMENT",
        priority=Importance.CRITICAL,
        answer_type=AnswerType.NUMBER,
        status=QuestionStatus.PENDING,
    )
    mock_initial_analysis = InitialAnalysisResult(
        story_objective="Promote high-end perfume",
        characters=[CharacterAnalysisItem(name="Model", description="Woman in satin gown")],
        gaps=[mock_gap],
        questions=[mock_question],
    )

    from app.graph.nodes import analyze_script
    with patch.object(analyze_script.llm_service, "generate_structured", new=AsyncMock(return_value=mock_initial_analysis)):
        initial_state = {
            "project_id": "test-interactive-session-001",
            "original_script": "A woman walks in a botanical garden with a glass perfume bottle.",
            "script_source": "text",
            "selected_tool": "Veo",
        }

        # Step 1: Run graph initial invocation
        state_after_init = await graph.ainvoke(initial_state, config)

        # Graph MUST be paused at WAITING_FOR_USER!
        assert state_after_init["status"] == AgentStatus.WAITING_FOR_USER
        assert len(state_after_init["questions"]) == 1
        generated_qid = state_after_init["questions"][0].id
        assert bool(generated_qid)
        assert state_after_init["questions"][0].question == "What is the desired duration of this commercial?"

    # Step 2: User provides answer
    user_answer = Answer(question_id=generated_qid, answer="8 seconds", answer_type=AnswerType.TEXT)

    # Resume graph by updating state with answers
    await graph.aupdate_state(config, {"new_answers": [user_answer]})

    # Mock Re-Analysis returning resolved gap and no new questions
    resolved_gap = Gap(
        id="gap-dur-1",
        category=GapCategory.OUTPUT_REQUIREMENT,
        importance=Importance.CRITICAL,
        title="Unknown Duration",
        description="Duration specified",
        evidence="User answered 8 seconds",
        status=GapStatus.RESOLVED,
    )
    mock_reanalysis = ReAnalysisResult(gaps=[resolved_gap], questions=[])

    from app.graph.nodes import re_analyze, build_video_spec, generate_scenes_and_prompts, review_prompts, generate_images, generate_videos
    from app.schemas.specification import VideoSpecification, OutputRequirements
    from app.schemas.generation import GenerationResult, GeneratedPromptItem, GeneratedScenePlan

    mock_spec = VideoSpecification(
        project_id="test-interactive-session-001",
        title="Perfume Garden",
        output_requirements=OutputRequirements(duration_seconds=8, aspect_ratio="16:9"),
    )
    mock_generation = GenerationResult(
        scenes=[GeneratedScenePlan(scene_id="sc_1", scene_number=1, title="Garden", purpose="Intro", start_time=0, end_time=8, duration_seconds=8)],
        total_duration=8.0,
        prompts=[GeneratedPromptItem(prompt_id="p_1", scene_id="sc_1", shot_id="shot_1", sequence_number=1, duration_seconds=8, prompt_text="Cinematic garden shot")],
    )

    async def mock_generate_structured_resumption(prompt, schema, **kwargs):
        if schema == ReAnalysisResult:
            return mock_reanalysis
        elif schema == VideoSpecification:
            return mock_spec
        elif schema == GenerationResult:
            return mock_generation
        raise ValueError(f"Unexpected schema: {schema}")

    with patch("app.llm.llm_service.generate_structured", new=AsyncMock(side_effect=mock_generate_structured_resumption)), \
         patch("app.graph.nodes.generate_images.generate_images", new=AsyncMock(side_effect=lambda s: s)), \
         patch("app.graph.nodes.generate_videos.generate_videos", new=AsyncMock(side_effect=lambda s: {**s, "status": AgentStatus.COMPLETED})):

        final_state = await graph.ainvoke(None, config)

        # After re-analysis resolved the gap, it successfully proceeded all the way to prompts & video generation phase!
        assert final_state["status"] in (AgentStatus.GENERATING_VIDEOS, AgentStatus.COMPLETED)
        assert final_state.get("prompt_set") is not None
        assert len(final_state["prompt_set"].prompts) == 1
        assert final_state["prompt_set"].prompts[0].prompt_text == "Cinematic garden shot"


@pytest.mark.asyncio
async def test_analysis_error_halts_graph_immediately():
    """Verify that if analyze_script fails, the graph halts at END with ERROR and never calls build_video_spec."""
    memory = MemorySaver(serde=serde)
    graph = build_graph(memory)
    config = {"configurable": {"thread_id": "test-error-session-001"}}

    from app.graph.nodes import analyze_script, build_video_spec
    from app.llm import LLMException

    # Simulate Gemini 400 Bad Request / LLMException during analysis
    with patch.object(analyze_script.llm_service, "generate_structured", new=AsyncMock(side_effect=LLMException("Vertex AI 400 Bad Request: schema invalid"))), \
         patch.object(build_video_spec, "build_video_spec", new=AsyncMock()) as mock_build_spec:

        initial_state = {
            "project_id": "test-error-session-001",
            "original_script": "A simple test script",
            "script_source": "text",
        }

        final_state = await graph.ainvoke(initial_state, config)

        # Graph MUST be in ERROR status and stopped
        assert final_state["status"] == AgentStatus.ERROR
        assert "Vertex AI 400 Bad Request" in final_state.get("error", "")

        # build_video_spec MUST NEVER be called when analysis failed!
        mock_build_spec.assert_not_called()
