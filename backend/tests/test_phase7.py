import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.graph.state import AgentState
from app.schemas.agent import Gap, GapCategory, Importance, GapStatus, AgentStatus, Answer, AnswerType
from app.schemas.specification import (
    VideoSpecification, SpecSource, SpecStatus, CharacterSpec, LocationSpec, 
    ProductSpec, ActionSpec, OutputRequirements, ConstraintSpec, ReferenceAsset
)
from app.graph.nodes.build_video_spec import build_video_spec
from app.graph.graph import build_graph

def test_specification_models_valid():
    """Test 1-9: VideoSpecification and all sub-models creation and validation."""
    spec = VideoSpecification(
        project_id="test-proj",
        title="Test Project",
        characters=[
            CharacterSpec(id="c1", name="Woman", source=SpecSource.USER)
        ],
        locations=[
            LocationSpec(id="l1", name="Hotel Room", source=SpecSource.SCRIPT)
        ],
        products=[
            ProductSpec(id="p1", name="Perfume", source=SpecSource.SCRIPT)
        ],
        actions=[
            ActionSpec(id="a1", actor_id="c1", action="picks up", target_object_id="p1")
        ],
        constraints=[
            ConstraintSpec(id="cons1", description="Must be 10 seconds", type="HARD_CONSTRAINT", source=SpecSource.USER)
        ],
        output_requirements=OutputRequirements(duration_seconds=10, source=SpecSource.USER)
    )
    
    assert spec.project_id == "test-proj"
    assert spec.characters[0].name == "Woman"
    assert spec.characters[0].source == SpecSource.USER
    assert spec.output_requirements.duration_seconds == 10

def test_traceability_and_enums():
    """Test 10-14: Source traceability and enum validation."""
    char = CharacterSpec(id="c1", name="Man", source="USER") # Pydantic will coerce to SpecSource.USER
    assert char.source == SpecSource.USER
    
    # Confidence validation (not strictly enforced by Pydantic here unless we add validators, but testing assignment)
    from app.schemas.specification import SourcedField
    field = SourcedField(value="Blue", source=SpecSource.INFERRED, confidence=0.8)
    assert field.confidence == 0.8

@patch('app.graph.nodes.build_video_spec.llm_service')
@pytest.mark.asyncio
async def test_build_video_spec_ready(mock_llm):
    """Test 18: READY status validation and 25: build_video_spec node."""
    
    # Mock LLM returning a valid spec with NO blocking unresolved items
    mock_spec = VideoSpecification(project_id="proj-1", unresolved_items=[])
    mock_llm.generate_structured = AsyncMock(return_value=mock_spec)
    
    state: AgentState = {
        "project_id": "proj-1",
        "original_script": "A woman walks in.",
        "gaps": []
    }
    
    new_state = await build_video_spec(state)
    assert new_state["status"] == AgentStatus.VALIDATING
    assert new_state["video_specification"].status == SpecStatus.READY

@patch('app.graph.nodes.build_video_spec.llm_service')
@pytest.mark.asyncio
async def test_build_video_spec_blocked(mock_llm):
    """Test 17 & 19 & 41: BLOCKED status validation and unresolved gaps."""
    
    # Mock LLM returning a valid spec
    mock_spec = VideoSpecification(project_id="proj-1", unresolved_items=[])
    mock_llm.generate_structured = AsyncMock(return_value=mock_spec)
    
    # Provide a CRITICAL open gap in the state
    state: AgentState = {
        "project_id": "proj-1",
        "gaps": [
            Gap(
                id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, 
                description="Age missing", evidence="missing", status=GapStatus.OPEN
            )
        ]
    }
    
    new_state = await build_video_spec(state)
    
    # build_video_spec should force unresolved items for CRITICAL open gaps
    spec = new_state["video_specification"]
    assert len(spec.unresolved_items) == 1
    assert spec.unresolved_items[0].blocking == True
    assert spec.status == SpecStatus.BLOCKED


def test_hallucination_prevention_prompt():
    """Test 38: Hallucination prevention prompt inclusion."""
    from app.prompts.video_specification import VIDEO_SPECIFICATION_PROMPT
    assert "DO NOT invent technical filmmaking parameters" in VIDEO_SPECIFICATION_PROMPT
    assert "DO NOT invent character attributes" in VIDEO_SPECIFICATION_PROMPT

def test_user_override_precedence_prompt():
    """Test 40: User override test (prompt instructions)."""
    from app.prompts.video_specification import VIDEO_SPECIFICATION_PROMPT
    assert "USER_CLARIFICATION > EXPLICIT_SCRIPT" in VIDEO_SPECIFICATION_PROMPT

def test_continuity_bible():
    """Test 39: Continuity test (model structure)."""
    spec = VideoSpecification(
        project_id="proj-1"
    )
    spec.continuity_bible.characters.append(
        CharacterSpec(id="c1", name="Woman", clothing="black evening gown")
    )
    spec.continuity_bible.products.append(
        ProductSpec(id="p1", name="Bottle", color="green")
    )
    spec.continuity_bible.locations.append(
        LocationSpec(id="l1", name="Hotel", type="luxury hotel room")
    )
    
    assert spec.continuity_bible.characters[0].clothing == "black evening gown"
    assert spec.continuity_bible.products[0].color == "green"
    assert spec.continuity_bible.locations[0].type == "luxury hotel room"
