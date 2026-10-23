from ..config import AIConfig
from .base import LLMAdapter
from .mock import MockLLMAdapter
from .ollama import OllamaAdapter
from .sagemaker import SageMakerAdapter


def create_adapter(config: AIConfig | None = None) -> LLMAdapter:
    config = config or AIConfig.from_env()
    backend = (config.model_backend or "mock").strip().lower()
    if backend == "ollama":
        return OllamaAdapter(base_url=config.ollama_base_url, model=config.model_id)
    if backend == "sagemaker":
        return SageMakerAdapter(
            endpoint_name=config.sagemaker_endpoint_name, model_id=config.model_id
        )
    return MockLLMAdapter(model_id=config.model_id)
