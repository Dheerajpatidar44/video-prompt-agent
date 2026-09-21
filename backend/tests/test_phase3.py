import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.services.script_service import ScriptService
from app.schemas.script import ScriptAnalysis
from app.llm.ollama import LLMService, LLMException
from app.graph.state import AgentState
from app.graph.nodes.analyze_script import analyze_script

client = TestClient(app)

def test_normalization():
    raw_text = "Hello    world.\n\n\n\nNew line."
    norm = ScriptService.normalize_text(raw_text)
    assert norm == "Hello world.\n\nNew line."

def test_empty_text_ingestion():
    with pytest.raises(ValueError, match="Input text is empty."):
        ScriptService.ingest_text("   \n ")

def test_txt_parsing():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
        tmp.write("Test script.")
        tmp_path = tmp.name
    
    try:
        doc = ScriptService.ingest_file(tmp_path, "txt", "test.txt")
        assert doc.original_text == "Test script."
        assert doc.source_type == "txt"
    finally:
        os.remove(tmp_path)

def test_llm_service_configuration():
    service = LLMService()
    assert service.base_url is not None
    assert service.model_name is not None

@patch('app.llm.ollama.httpx.get')
def test_ollama_unavailability(mock_get):
    mock_get.side_effect = Exception("Connection refused")
    service = LLMService()
    assert service.check_health() is False
    with pytest.raises(LLMException, match="Ollama is not running."):
        service.generate_structured("test", ScriptAnalysis)

@patch('app.llm.ollama.httpx.get')
@patch.object(LLMService, 'check_model')
def test_unavailable_model(mock_check_model, mock_get):
    mock_get.return_value.status_code = 200
    mock_check_model.return_value = False
    
    service = LLMService()
    # Mocking check_health manually to isolate check_model failure
    service.check_health = MagicMock(return_value=True)
    
    with pytest.raises(LLMException, match="not available"):
        service.generate_structured("test", ScriptAnalysis)

@patch('app.graph.nodes.analyze_script.LLMService')
def test_analyze_script_node_with_mock(mock_llm_service):
    mock_instance = mock_llm_service.return_value
    mock_analysis = ScriptAnalysis(story_summary="Mocked story")
    mock_instance.generate_structured.return_value = mock_analysis
    
    state: AgentState = {"original_script": "Test script."}
    new_state = analyze_script(state)
    
    assert new_state["analysis"]["story_summary"] == "Mocked story"
    assert new_state["status"] == "ANALYZING"
    assert new_state["error"] is None

@patch('app.api.routes.scripts.graph.invoke')
def test_analyze_endpoint_with_text(mock_invoke):
    mock_invoke.return_value = {
        "analysis": {"story_summary": "Endpoint mock story"},
        "status": "ANALYZING",
        "error": None
    }
    
    response = client.post("/api/v1/scripts/analyze", data={"text": "Test from endpoint."})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["script"]["original_text"] == "Test from endpoint."
    assert data["analysis"]["story_summary"] == "Endpoint mock story"
