from app.core.config import settings

class ModelConfig:
    @staticmethod
    def get_ollama_base_url() -> str:
        return settings.ollama_base_url
        
    @staticmethod
    def get_model_name() -> str:
        return settings.ollama_model
