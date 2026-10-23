import json
from typing import Callable

from ..config import DEFAULT_SAGEMAKER_MODEL_ID, PAYLOAD_MODES
from ..errors import (
    LLMAuthError,
    LLMEndpointError,
    LLMResponseError,
    LLMThrottledError,
    LLMTimeoutError,
    LLMUnavailableError,
    ModelNotConfiguredError,
)
from ..redaction import redact
from .base import LLMAdapter, LLMRequest, LLMResponse

InvokeFn = Callable[[str], str]

VALIDATION_GATE = (
    "SageMaker inference is not configured. Before enabling: validate the exact "
    "model repo ID and license, Transformers/vLLM support for that checkpoint, the "
    "chosen SageMaker container (LoRA vs merged artifact), instance memory, and "
    "request/response parity with LLMResponse. No endpoint is created by this code."
)

AUTH_ERROR_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidSignatureException",
    "SignatureDoesNotMatch",
    "AuthFailure",
    "SecurityTokenExpired",
}
AUTH_ERROR_CLASSES = {"NoCredentialsError", "PartialCredentialsError"}
TIMEOUT_ERROR_CLASSES = {"ReadTimeoutError", "ConnectTimeoutError"}
TIMEOUT_ERROR_CODES = {"RequestTimeout", "RequestTimeoutException"}
THROTTLE_ERROR_CODES = {
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "ModelThrottledException",
}
ENDPOINT_ERROR_CODES = {
    "ResourceNotFound",
    "ResourceNotFoundedException",
    "EndpointNotFound",
    "EndpointNotFoundException",
    "ModelNotReady",
    "ModelNotReadyException",
    "ServiceUnavailable",
    "ServiceUnavailableException",
    "InternalFailure",
    "InternalServerError",
    "ValidationException",
}


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            code = error.get("Code")
            if isinstance(code, str):
                return code
    return ""


def classify_invocation_error(exc: Exception) -> LLMUnavailableError:
    code = _error_code(exc)
    name = type(exc).__name__
    message = redact(f"sagemaker invocation failed ({code or name}): {exc}")
    if name in AUTH_ERROR_CLASSES or code in AUTH_ERROR_CODES:
        return LLMAuthError(message)
    if name in TIMEOUT_ERROR_CLASSES or "Timeout" in name or code in TIMEOUT_ERROR_CODES:
        return LLMTimeoutError(message)
    if code in THROTTLE_ERROR_CODES:
        return LLMThrottledError(message)
    if code in ENDPOINT_ERROR_CODES or "NotFound" in name:
        return LLMEndpointError(message)
    return LLMEndpointError(message)


class SageMakerAdapter(LLMAdapter):
    def __init__(
        self,
        endpoint_name: str = "",
        model_id: str = "",
        region: str = "",
        payload_mode: str = "planproof",
        timeout_s: int = 120,
        invoke_client=None,
        invoke_fn: InvokeFn | None = None,
    ):
        if payload_mode not in PAYLOAD_MODES:
            raise ValueError(
                f"unknown sagemaker payload mode {payload_mode!r}; expected one of {PAYLOAD_MODES}"
            )
        self.endpoint_name = endpoint_name
        self.model_id = model_id or (
            f"sagemaker/{endpoint_name}" if endpoint_name else f"sagemaker/{DEFAULT_SAGEMAKER_MODEL_ID}"
        )
        self.region = region
        self.payload_mode = payload_mode
        self.timeout_s = timeout_s
        self._client = invoke_client
        self._invoke_fn = invoke_fn

    @property
    def endpoint_configured(self) -> bool:
        return bool(self.endpoint_name)

    def _require_endpoint(self) -> None:
        if not self.endpoint_name:
            raise ModelNotConfiguredError(VALIDATION_GATE)

    def _build_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ModelNotConfiguredError(
                "boto3/botocore is not installed; install the 'aws' extra "
                "(pip install -e 'ai/[aws]') before enabling MODEL_BACKEND=sagemaker"
            ) from exc
        self._client = boto3.client(
            "sagemaker-runtime",
            region_name=self.region or None,
            config=Config(
                connect_timeout=min(self.timeout_s, 10),
                read_timeout=self.timeout_s,
                retries={"max_attempts": 1},
            ),
        )
        return self._client

    def _build_payload(self, request: LLMRequest) -> dict:
        if self.payload_mode == "planproof":
            return {
                "prompt": redact(request.prompt),
                "diagnostics": redact(request.diagnostics),
                "max_tokens": request.max_tokens,
                "model_id": self.model_id,
            }
        prompt = redact(request.prompt)
        if request.diagnostics:
            prompt = f"{prompt}\n\nDiagnostics (redacted):\n{redact(request.diagnostics)}"
        if self.payload_mode == "hf":
            return {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": request.max_tokens,
                    "do_sample": False,
                    "return_full_text": False,
                },
            }
        return {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": request.max_tokens,
            "temperature": 0,
            "model": self.model_id,
        }

    def _invoke(self, payload: dict) -> str:
        body = json.dumps(payload)
        if self._invoke_fn is not None:
            try:
                return self._invoke_fn(body)
            except LLMUnavailableError:
                raise
            except Exception as exc:
                raise classify_invocation_error(exc) from exc
        client = self._build_client()
        try:
            response = client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Accept="application/json",
                Body=body,
            )
        except LLMUnavailableError:
            raise
        except Exception as exc:
            raise classify_invocation_error(exc) from exc
        raw = response.get("Body") if isinstance(response, dict) else None
        if raw is None:
            raise LLMResponseError("sagemaker response missing body")
        if hasattr(raw, "read"):
            raw = raw.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            return raw
        raise LLMResponseError(f"unexpected sagemaker body type: {type(raw).__name__}")

    def _parse(self, text: str) -> LLMResponse:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseError(
                redact(f"endpoint returned non-JSON payload: {exc}")
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError(
                f"endpoint returned {type(data).__name__}, expected a JSON object"
            )
        if self.payload_mode == "planproof":
            if isinstance(data.get("rationale"), str):
                return LLMResponse(
                    patch=data.get("patch") if isinstance(data.get("patch"), str) else None,
                    rationale=data["rationale"],
                    model_id=str(data.get("model_id") or self.model_id),
                    finish_reason=str(data.get("finish_reason", "stop")),
                    raw=data,
                )
            if isinstance(data.get("generation"), str):
                return LLMResponse(
                    patch=None,
                    rationale=data["generation"],
                    model_id=self.model_id,
                    finish_reason="stop",
                    raw=data,
                )
            raise LLMResponseError("endpoint response missing 'rationale'")
        if self.payload_mode == "hf":
            generated = data.get("generated_text")
            if isinstance(generated, list) and generated:
                first = generated[0]
                generated = first.get("generated_text") if isinstance(first, dict) else None
            if isinstance(generated, str) and generated.strip():
                return LLMResponse(
                    patch=None,
                    rationale=generated,
                    model_id=self.model_id,
                    finish_reason=str(data.get("finish_reason", "stop")),
                    raw=data,
                )
            raise LLMResponseError("endpoint response missing 'generated_text'")
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                content = None
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    content = message["content"]
                elif isinstance(first.get("text"), str):
                    content = first["text"]
                if isinstance(content, str) and content.strip():
                    return LLMResponse(
                        patch=None,
                        rationale=content,
                        model_id=self.model_id,
                        finish_reason=str(first.get("finish_reason") or data.get("finish_reason") or "stop"),
                        raw=data,
                    )
        raise LLMResponseError("endpoint response missing 'choices[0].message.content'")

    def complete(self, request: LLMRequest) -> LLMResponse:
        self._require_endpoint()
        payload = self._build_payload(request)
        body_text = self._invoke(payload)
        return self._parse(body_text)
