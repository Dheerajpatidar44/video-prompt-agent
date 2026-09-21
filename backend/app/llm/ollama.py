import httpx
from typing import TypeVar, Type
from pydantic import BaseModel
import ollama
from app.llm.model_config import ModelConfig

T = TypeVar("T", bound=BaseModel)

class LLMException(Exception):
    pass

class LLMService:
    def __init__(self):
        self.base_url = ModelConfig.get_ollama_base_url()
        self.model_name = ModelConfig.get_model_name()
        self.client = ollama.Client(host=self.base_url)

    def check_health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/")
            return response.status_code == 200
        except Exception:
            return False

    def check_model(self) -> bool:
        try:
            response = self.client.list()
            models = response.get("models", [])
            model_names = [m["model"] for m in models]
            return self.model_name in model_names or f"{self.model_name}:latest" in model_names
        except Exception:
            return False

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        if not self.check_health():
            raise LLMException("Ollama is not running. Start Ollama and try again.")
        if not self.check_model():
            raise LLMException(f"The configured local model '{self.model_name}' is not available. Install it in Ollama and try again.")
            
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=schema.model_json_schema()
            )
            content = response["message"]["content"]
            return schema.model_validate_json(content)
        except Exception as e:
            raise LLMException(f"Failed to generate structured output: {str(e)}")
