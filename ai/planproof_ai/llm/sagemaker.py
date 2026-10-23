from typing import Callable

from ..errors import LLMResponseError, ModelNotConfiguredError
from .base import LLMAdapter, LLMRequest, LLMResponse

InvokeFn = Callable[[str], str]

VALIDATION_GATE = (
    "SageMaker inference is not configured. Before enabling: validate the exact "
    "model repo ID and license, Transformers/LoRA support for that checkpoint, the "
    "chosen SageMaker container (LoRA vs merged artifact), instance memory, and "
    "request/response parity with LLMResponse. No endpoint is created by this code."
)


class SageMakerAdapter(LLMAdapter):
    def __init__(self, endpoint_name: str = "", model_id: str = "",
                 invoke_fn: InvokeFn | None = None):
        self.endpoint_name = endpoint_name
        self.model_id = model_id or (f"sagemaker/{endpoint_name}" if endpoint_name else "sagemaker/unconfigured")
        self._invoke = invoke_fn

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.endpoint_name:
            raise ModelNotConfiguredError(VALIDATION_GATE)
        if self._invoke is None:
            raise ModelNotConfiguredError(VALIDATION_GATE)
        payload = {
            "prompt": request.prompt,
            "diagnostics": request.diagnostics,
            "max_tokens": request.max_tokens,
        }
        import json

        raw_text = self._invoke(json.dumps(payload))
        try:
            data = json.loads(raw_text)
        except (TypeError, ValueError) as exc:
            raise LLMResponseError(f"endpoint returned non-JSON payload: {exc}") from exc
        if isinstance(data, dict) and "rationale" in data:
            return LLMResponse(
                patch=data.get("patch"),
                rationale=str(data.get("rationale", "")),
                model_id=str(data.get("model_id") or self.model_id),
                finish_reason=str(data.get("finish_reason", "stop")),
                raw=data,
            )
        if isinstance(data, dict) and "generation" in data:
            return LLMResponse(
                patch=None,
                rationale=str(data.get("generation", "")),
                model_id=self.model_id,
                finish_reason="stop",
                raw=data,
            )
        raise LLMResponseError("endpoint response missing 'rationale'/'generation'")
