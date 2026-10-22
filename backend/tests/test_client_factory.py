import pytest
from pydantic import SecretStr
from app.core.config import settings
from app.services.video_generation.client_factory import get_video_client, reset_video_client
from app.services.video_generation.mock_client import MockVideoClient
from app.services.video_generation.veo_client import VeoClient
from app.services.video_generation.base_client import PermanentVideoError

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

def test_veo_client_factory(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_provider", "veo")
    monkeypatch.setattr(settings, "google_api_key", SecretStr("testkey123"))
    client = get_video_client()
    assert isinstance(client, VeoClient)
    assert get_video_client() is client

def test_reset_video_client_clears(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", True)
    client1 = get_video_client()
    reset_video_client()
    client2 = get_video_client()
    assert client1 is not client2

def test_blank_key_in_real_mode_raises(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_provider", "veo")
    monkeypatch.setattr(settings, "google_api_key", SecretStr(""))
    with pytest.raises(PermanentVideoError, match="GOOGLE_API_KEY is not set"):
        get_video_client()

def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_provider", "unknown_provider")
    with pytest.raises(ValueError, match="Unknown VIDEO_PROVIDER"):
        get_video_client()
