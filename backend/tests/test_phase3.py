import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import app
from app.services.script_service import ScriptService
from app.schemas.script import ScriptAnalysis
from app.llm.claude_client import LLMService, LLMException
from app.graph.state import AgentState
from app.graph.nodes.analyze_script import analyze_script
import anthropic

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
    # verify it initialized the model name from config
    assert service.model_name is not None
    # semaphore should be initialized
    assert service._semaphore is not None


@patch('app.llm.claude_client.AsyncAnthropic')
@pytest.mark.asyncio
async def test_llm_api_status_error(mock_anthropic):
    """Test that anthropic.APIStatusError is caught and raised as LLMException."""
    from app.llm.claude_client import LLMService
    
    service = LLMService()
    
    # Mock the client's messages.create method to raise APIStatusError
    mock_messages_create = AsyncMock(side_effect=anthropic.APIStatusError(
        message="Rate limit exceeded",
        response=MagicMock(),
        body={}
    ))
    
    # Create a mock client instance
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = mock_messages_create
    service.client = mock_client_instance
    
    with pytest.raises(LLMException, match="Claude API Status Error"):
        await service.generate_structured("test prompt", ScriptAnalysis)


@patch('app.llm.claude_client.AsyncAnthropic')
@pytest.mark.asyncio
async def test_llm_generic_error(mock_anthropic):
    """Test that generic exceptions are caught and raised as LLMException."""
    from app.llm.claude_client import LLMService
    
    service = LLMService()
    
    # Mock the client's messages.create method to raise Exception
    mock_messages_create = AsyncMock(side_effect=Exception("Connection reset by peer"))
    
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = mock_messages_create
    service.client = mock_client_instance
    
    with pytest.raises(LLMException, match="Claude call failed: Connection reset by peer"):
        await service.generate_structured("test prompt", ScriptAnalysis)


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
