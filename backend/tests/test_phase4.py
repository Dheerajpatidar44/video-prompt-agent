import pytest
from app.schemas.agent import Gap, Importance, GapCategory, GapDetectionResult
from app.graph.nodes.detect_gaps import deduplicate_gaps, sort_gaps, detect_gaps
from app.graph.state import AgentState
from pydantic import ValidationError
from unittest.mock import patch, MagicMock
from app.main import app
from fastapi.testclient import TestClient
from app.llm.ollama import LLMException

client = TestClient(app)

def test_gap_model_validation():
    # 1. Gap model validation
    gap = Gap(
        id="test_gap_1",
        category=GapCategory.CHARACTER,
        importance=Importance.CRITICAL,
        description="Character name missing",
        evidence="Script doesn't mention name"
    )
    assert gap.category == "CHARACTER"

def test_invalid_category_rejection():
    # 2. Invalid category rejection
    with pytest.raises(ValidationError):
        Gap(
            id="test_gap_1",
            category="INVALID_CAT",
            importance=Importance.CRITICAL,
            description="desc",
            evidence="ev"
        )

def test_invalid_severity_rejection():
    # 3. Invalid severity rejection
    with pytest.raises(ValidationError):
        Gap(
            id="test_gap_1",
            category=GapCategory.CHARACTER,
            importance="SUPER_CRITICAL",
            description="desc",
            evidence="ev"
        )

def test_missing_evidence_validation():
    # 4. Missing evidence validation
    with pytest.raises(ValidationError):
        Gap(
            id="test_gap_1",
            category=GapCategory.CHARACTER,
            importance=Importance.CRITICAL,
            description="desc"
        )

def test_duplicate_gap_removal():
    # 5. Duplicate gap removal
    gaps = [
        Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, title="No Name", description="d", evidence="e"),
        Gap(id="g2", category=GapCategory.CHARACTER, importance=Importance.IMPORTANT, title="No Name", description="d2", evidence="e2"),
        Gap(id="g3", category=GapCategory.LOCATION, importance=Importance.CRITICAL, title="No Name", description="d3", evidence="e3"),
    ]
    unique = deduplicate_gaps(gaps)
    assert len(unique) == 2
    assert unique[0].id == "g1"
    assert unique[1].id == "g3"

def test_gap_prioritization():
    # 6. Gap prioritization
    gaps = [
        Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.INFERABLE, description="d", evidence="e"),
        Gap(id="g2", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, description="d", evidence="e"),
        Gap(id="g3", category=GapCategory.CHARACTER, importance=Importance.IMPORTANT, description="d", evidence="e"),
        Gap(id="g4", category=GapCategory.CHARACTER, importance=Importance.OPTIONAL, description="d", evidence="e"),
    ]
    sorted_g = sort_gaps(gaps)
    assert sorted_g[0].importance == Importance.CRITICAL
    assert sorted_g[1].importance == Importance.IMPORTANT
    assert sorted_g[2].importance == Importance.OPTIONAL
    assert sorted_g[3].importance == Importance.INFERABLE

@patch('app.graph.nodes.detect_gaps.LLMService')
def test_mock_llm_gap_detection(mock_llm_service):
    # 11. Mock LLM gap detection
    mock_instance = mock_llm_service.return_value
    mock_result = GapDetectionResult(gaps=[
        Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, title="T", description="D", evidence="E")
    ])
    mock_instance.generate_structured.return_value = mock_result
    
    state: AgentState = {"original_script": "Test script."}
    new_state = detect_gaps(state)
    
    assert len(new_state["gaps"]) == 1
    assert new_state["gaps"][0].id == "g1"
    assert new_state["status"] == "ANALYZING"

@patch('app.graph.nodes.detect_gaps.LLMService')
def test_invalid_llm_output(mock_llm_service):
    # 12. Invalid LLM structured output
    mock_instance = mock_llm_service.return_value
    mock_instance.generate_structured.side_effect = Exception("LLM Error")
    
    state: AgentState = {"original_script": "Test script."}
    new_state = detect_gaps(state)
    assert new_state["status"] == "ERROR"
    assert "LLM Error" in new_state["error"]

@patch('app.api.routes.scripts.graph.invoke')
def test_api_integration(mock_invoke):
    # 15. API integration
    mock_invoke.return_value = {
        "analysis": {"story_summary": "Summary"},
        "gaps": [Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, title="T", description="D", evidence="E")],
        "status": "ANALYZING",
        "error": None
    }
    
    response = client.post("/api/v1/scripts/analyze", data={"text": "Test script"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["gaps"]["total"] == 1
    assert data["gaps"]["critical"] == 1

def test_graph_routing_terminates():
    # 14. Graph terminates at END on both branches (implicitly tested via build_graph)
    # The actual graph in Phase 3 is a placeholder. Let's invoke it with an initial state
    # that routes to ASK_QUESTIONS, ensuring it doesn't hang.
    from app.graph.graph import build_graph
    graph = build_graph()
    
    # Run a thread
    config = {"configurable": {"thread_id": "test-routing"}}
    
    # We will patch detect_gaps to return a CRITICAL gap so it branches to ASK_QUESTIONS
    with patch('app.graph.nodes.detect_gaps.LLMService') as mock_llm:
        mock_instance = mock_llm.return_value
        mock_result = GapDetectionResult(gaps=[
            Gap(id="g1", category=GapCategory.CHARACTER, importance=Importance.CRITICAL, title="T", description="D", evidence="E")
        ])
        mock_instance.generate_structured.return_value = mock_result
        
        with patch('app.graph.nodes.analyze_script.LLMService') as mock_llm_analyze:
            with patch('app.graph.nodes.ask_questions.LLMService') as mock_llm_ask:
                from app.schemas.script import ScriptAnalysis
                mock_analyze_instance = mock_llm_analyze.return_value
                mock_analyze_instance.generate_structured.return_value = ScriptAnalysis(story_summary="Sum")
                
                from app.schemas.agent import QuestionGenerationResult
                mock_ask_instance = mock_llm_ask.return_value
                mock_ask_instance.generate_structured.return_value = QuestionGenerationResult(questions=[])
                
                initial_state = {"project_id": "test-1", "original_script": "script content"}
                final_state = graph.invoke(initial_state, config)
                
                # Since ASK_QUESTIONS branch placeholder exists and goes to END, it should complete.
                assert final_state["status"] == "WAITING_FOR_USER" # ask_questions placeholder sets this
