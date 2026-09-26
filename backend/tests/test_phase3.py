import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

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

@patch('app.llm.ollama.httpx.AsyncClient.get')
@patch('app.llm.ollama.ollama.AsyncClient.list')
@pytest.mark.asyncio
async def test_ollama_unavailability(mock_list, mock_get):
    mock_get.side_effect = Exception("Connection refused")
    mock_list.side_effect = Exception("Connection refused")
    
    from app.llm.ollama import llm_service
    llm_service._health_ok = False
    llm_service._model_ok = False
    llm_service._last_health_check = 0.0
    llm_service._last_model_check = 0.0
    
    assert await llm_service.check_health() is False
    with pytest.raises(LLMException, match="Ollama is not running."):
        await llm_service.generate_structured("test", ScriptAnalysis)

@patch('app.llm.ollama.ollama.AsyncClient.list')
@pytest.mark.asyncio
async def test_unavailable_model(mock_list):
    mock_list.return_value = {"models": []}
    
    from app.llm.ollama import llm_service
    llm_service._health_ok = False
    llm_service._model_ok = False
    llm_service._last_model_check = 0.0
    
    with patch.object(llm_service, 'check_health', new=AsyncMock(return_value=True)):
        with pytest.raises(LLMException, match="not available"):
            await llm_service.generate_structured("test", ScriptAnalysis)

@patch('app.graph.nodes.analyze_script.llm_service')
@pytest.mark.asyncio
async def test_analyze_script_node_with_mock(mock_llm_service):
    from app.schemas.script import InitialAnalysisResult
    mock_analysis = InitialAnalysisResult(story_summary="Mocked story")
    mock_llm_service.generate_structured = AsyncMock(return_value=mock_analysis)
    
    state: AgentState = {"original_script": "Test script."}
    new_state = await analyze_script(state)
    
    assert new_state["analysis"]["story_summary"] == "Mocked story"
    assert new_state["status"] == "ANALYZING"
    assert new_state["error"] is None

@patch('app.api.routes.scripts.graph.ainvoke')
def test_analyze_endpoint_with_text(mock_ainvoke):
    # ainvoke returns a coroutine, so mock its return value
    # But fastAPI will await it properly when called.
    from app.schemas.agent import AgentStatus
    async def mock_coro(*args, **kwargs):
        return {
            "analysis": {"story_summary": "Endpoint mock story"},
            "status": AgentStatus.ANALYZING,
            "error": None
        }
    mock_ainvoke.side_effect = mock_coro
    
    response = client.post("/api/v1/scripts/analyze", data={"text": "Test from endpoint."})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ANALYZING"
    assert data["script"]["original_text"] == "Test from endpoint."
    assert data["analysis"]["story_summary"] == "Endpoint mock story"
