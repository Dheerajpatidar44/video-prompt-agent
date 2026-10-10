import pytest
from app.core.config import settings
from app.services.video_generation.client_factory import get_video_client, reset_video_client
from app.services.video_generation.mock_client import MockVideoClient
from app.services.video_generation.wavespeed_client import WaveSpeedClient

@pytest.fixture(autouse=True)
def reset_client():
    reset_video_client()
    yield
    reset_video_client()

def test_mock_client_factory(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", True)
    client = get_video_client()
    assert isinstance(client, MockVideoClient)
    assert get_video_client() is client

def test_wavespeed_client_factory(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_provider", "wavespeed")
    monkeypatch.setattr(settings.wavespeed_api_key, "get_secret_value", lambda: "testkey")
    client = get_video_client()
    assert isinstance(client, WaveSpeedClient)
    assert get_video_client() is client

def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_provider", "unknown")
    with pytest.raises(ValueError):
        get_video_client()
