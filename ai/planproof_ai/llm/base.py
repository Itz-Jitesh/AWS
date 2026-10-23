from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMRequest:
    prompt: str
    diagnostics: str = ""
    max_tokens: int = 2048


@dataclass
class LLMResponse:
    patch: str | None
    rationale: str
    model_id: str
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)


class LLMAdapter(ABC):
    model_id: str = "unknown"

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
