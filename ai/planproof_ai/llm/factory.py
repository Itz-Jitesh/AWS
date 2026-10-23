from ..config import AIConfig
from ..errors import ModelNotConfiguredError
from .base import LLMAdapter
from .mock import MockLLMAdapter
from .ollama import OllamaAdapter
from .sagemaker import SageMakerAdapter


def resolve_backend(config: AIConfig) -> str:
    backend = (config.model_backend or "").strip().lower()
    if backend:
        return backend
    if config.sagemaker_endpoint_name:
        return "sagemaker"
    return "mock"


def create_adapter(config: AIConfig | None = None) -> LLMAdapter:
    config = config or AIConfig.from_env()
    backend = resolve_backend(config)
    if backend == "ollama":
        return OllamaAdapter(base_url=config.ollama_base_url, model=config.model_id)
    if backend == "sagemaker":
        return SageMakerAdapter(
            endpoint_name=config.sagemaker_endpoint_name,
            model_id=config.model_id,
            region=config.sagemaker_region,
            payload_mode=config.sagemaker_payload_mode,
            timeout_s=config.sagemaker_timeout_s,
        )
    if backend == "mock":
        return MockLLMAdapter(model_id=config.model_id)
    raise ModelNotConfiguredError(
        f"unknown MODEL_BACKEND {backend!r}; expected one of: mock, ollama, sagemaker. "
        "Refusing to fall back to a mock backend implicitly."
    )
