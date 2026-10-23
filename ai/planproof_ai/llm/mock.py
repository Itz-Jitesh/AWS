from ..errors import LLMResponseError
from .base import LLMAdapter, LLMRequest, LLMResponse


class MockLLMAdapter(LLMAdapter):
    def __init__(self, responses: list[LLMResponse] | None = None, model_id: str = "mock-llm-v1"):
        self.model_id = model_id
        self._responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMResponseError("MockLLMAdapter has no preset responses left")
        if len(self._responses) > 1:
            response = self._responses.pop(0)
        else:
            response = self._responses[0]
        return response
