"""Unit tests for the SageMaker adapter using MOCKED AWS SDK calls.

No network, no AWS credentials, and no real endpoint are used here. The boto3
`sagemaker-runtime` client is replaced by an in-process fake whose
`invoke_endpoint` returns canned payloads or raises fake AWS-style errors.
Live-endpoint verification lives in tests/test_sagemaker_live.py and is
skipped unless explicitly enabled.
"""

import io
import json
import sys

import pytest

from planproof_ai.config import PAYLOAD_MODES
from planproof_ai.errors import (
    LLMAuthError,
    LLMEndpointError,
    LLMResponseError,
    LLMThrottledError,
    LLMTimeoutError,
    ModelNotConfiguredError,
)
from planproof_ai.llm.base import LLMRequest
from planproof_ai.llm.sagemaker import SageMakerAdapter, classify_invocation_error

REQ = LLMRequest(prompt="prompt", diagnostics="diag", max_tokens=128)


class MockedAWSClient:
    """Fake sagemaker-runtime client. Records calls, returns canned bodies."""

    def __init__(self, body=None, error=None):
        self.body = body
        self.error = error
        self.calls = []

    def invoke_endpoint(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"Body": io.BytesIO(self.body)}


def aws_error(code, message="aws failure"):
    err = Exception(message)
    err.response = {"Error": {"Code": code, "Message": message}}
    return err


class NoCredentialsError(Exception):
    pass


class ReadTimeoutError(Exception):
    pass


ENVELOPE_OK = json.dumps(
    {
        "patch": "--- a/main.tf\n+++ b/main.tf\n",
        "rationale": "made bucket private",
        "model_id": "google/gemma-4-E4B-it",
        "finish_reason": "stop",
    }
).encode()


def test_planproof_mode_success_round_trip_mocked():
    client = MockedAWSClient(body=ENVELOPE_OK)
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=client)
    response = adapter.complete(REQ)
    assert response.patch.startswith("--- a/main.tf")
    assert response.rationale == "made bucket private"
    assert response.model_id == "google/gemma-4-E4B-it"
    assert response.finish_reason == "stop"

    call = client.calls[0]
    assert call["EndpointName"] == "ep"
    assert call["ContentType"] == "application/json"
    assert call["Accept"] == "application/json"
    payload = json.loads(call["Body"])
    assert set(payload) == {"prompt", "diagnostics", "max_tokens", "model_id"}
    assert payload["prompt"] == "prompt"
    assert payload["diagnostics"] == "diag"
    assert payload["max_tokens"] == 128
    assert payload["model_id"] == "m"


def test_planproof_mode_accepts_lmi_generation_response_mocked():
    body = json.dumps({"generation": "plain text answer"}).encode()
    client = MockedAWSClient(body=body)
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=client)
    response = adapter.complete(REQ)
    assert response.rationale == "plain text answer"
    assert response.patch is None


def test_hf_mode_success_round_trip_mocked():
    body = json.dumps({"generated_text": "answer from hf handler"}).encode()
    client = MockedAWSClient(body=body)
    adapter = SageMakerAdapter(
        endpoint_name="ep", model_id="m", payload_mode="hf", invoke_client=client
    )
    response = adapter.complete(REQ)
    assert response.rationale == "answer from hf handler"
    payload = json.loads(client.calls[0]["Body"])
    assert payload["inputs"] == "prompt\n\nDiagnostics (redacted):\ndiag"
    assert payload["parameters"]["max_new_tokens"] == 128
    assert payload["parameters"]["do_sample"] is False
    assert "messages" not in payload


def test_openai_mode_success_round_trip_mocked():
    body = json.dumps(
        {"choices": [{"message": {"content": "openai style answer"}, "finish_reason": "stop"}]}
    ).encode()
    client = MockedAWSClient(body=body)
    adapter = SageMakerAdapter(
        endpoint_name="ep", model_id="m", payload_mode="openai", invoke_client=client
    )
    response = adapter.complete(REQ)
    assert response.rationale == "openai style answer"
    payload = json.loads(client.calls[0]["Body"])
    assert payload["messages"] == [{"role": "user", "content": "prompt\n\nDiagnostics (redacted):\ndiag"}]
    assert payload["max_tokens"] == 128
    assert payload["temperature"] == 0
    assert payload["model"] == "m"


def test_openai_mode_accepts_completions_text_response_mocked():
    body = json.dumps({"choices": [{"text": "completion style", "finish_reason": "stop"}]}).encode()
    client = MockedAWSClient(body=body)
    adapter = SageMakerAdapter(
        endpoint_name="ep", model_id="m", payload_mode="openai", invoke_client=client
    )
    response = adapter.complete(REQ)
    assert response.rationale == "completion style"


def test_missing_endpoint_fails_closed():
    adapter = SageMakerAdapter(endpoint_name="", model_id="m")
    with pytest.raises(ModelNotConfiguredError):
        adapter.complete(REQ)


def test_unknown_payload_mode_rejected_at_construction():
    with pytest.raises(ValueError, match="payload mode"):
        SageMakerAdapter(endpoint_name="ep", payload_mode="nope")
    assert set(PAYLOAD_MODES) == {"planproof", "hf", "openai"}


def test_missing_boto3_fails_closed(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(ModelNotConfiguredError, match="boto3"):
        adapter.complete(REQ)


def test_auth_failure_classified(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=aws_error("AccessDeniedException")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMAuthError) as excinfo:
        adapter.complete(REQ)
    assert excinfo.value.code == "llm_auth_error"


def test_missing_credentials_classified(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=NoCredentialsError("unable to locate credentials")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMAuthError):
        adapter.complete(REQ)


def test_throttling_classified(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=aws_error("ThrottlingException")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMThrottledError) as excinfo:
        adapter.complete(REQ)
    assert excinfo.value.code == "llm_throttled"


def test_timeout_classified(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=ReadTimeoutError("read timed out")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMTimeoutError) as excinfo:
        adapter.complete(REQ)
    assert excinfo.value.code == "llm_timeout"


def test_endpoint_not_found_classified(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=aws_error("EndpointNotFoundException")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMEndpointError) as excinfo:
        adapter.complete(REQ)
    assert excinfo.value.code == "llm_endpoint_error"


def test_unknown_aws_error_fails_closed_as_endpoint_error(monkeypatch):
    monkeypatch.setattr(
        SageMakerAdapter,
        "_build_client",
        lambda self: MockedAWSClient(error=aws_error("SomethingBrandNew")),
    )
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMEndpointError):
        adapter.complete(REQ)


def test_invoke_fn_errors_are_classified():
    def failing_invoke(payload: str) -> str:
        raise aws_error("ExpiredTokenException")

    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_fn=failing_invoke)
    with pytest.raises(LLMAuthError):
        adapter.complete(REQ)


def test_aws_error_details_are_redacted():
    secret = "aws_secret_access_key=super-secret-value-123"
    key = "AKIAIOSFODNN7EXAMPLE"
    exc = aws_error("AccessDeniedException", f"denied for {key} with {secret}")
    mapped = classify_invocation_error(exc)
    text = str(mapped)
    assert key not in text
    assert "super-secret-value-123" not in text
    assert "***REDACTED***" in text
    assert isinstance(mapped, LLMAuthError)


def test_prompt_secrets_are_redacted_before_send():
    captured = {}

    def invoke(payload: str) -> str:
        captured.update(json.loads(payload))
        return ENVELOPE_OK.decode()

    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_fn=invoke)
    adapter.complete(
        LLMRequest(prompt="token=abcdef123456", diagnostics="password=hunter2", max_tokens=8)
    )
    assert "abcdef123456" not in json.dumps(captured)
    assert "hunter2" not in json.dumps(captured)


def test_non_json_response_raises_response_error():
    client = MockedAWSClient(body=b"<html>gateway error</html>")
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=client)
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_json_array_response_raises_response_error():
    client = MockedAWSClient(body=b'["not", "an", "object"]')
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=client)
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_planproof_missing_rationale_raises_response_error():
    client = MockedAWSClient(body=b'{"foo": 1}')
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=client)
    with pytest.raises(LLMResponseError, match="rationale"):
        adapter.complete(REQ)


def test_hf_missing_generated_text_raises_response_error():
    client = MockedAWSClient(body=b'{"foo": 1}')
    adapter = SageMakerAdapter(
        endpoint_name="ep", model_id="m", payload_mode="hf", invoke_client=client
    )
    with pytest.raises(LLMResponseError, match="generated_text"):
        adapter.complete(REQ)


def test_openai_missing_choices_raises_response_error():
    client = MockedAWSClient(body=b'{"foo": 1}')
    adapter = SageMakerAdapter(
        endpoint_name="ep", model_id="m", payload_mode="openai", invoke_client=client
    )
    with pytest.raises(LLMResponseError, match="choices"):
        adapter.complete(REQ)


def test_response_without_body_raises_response_error(monkeypatch):
    class EmptyBodyClient:
        def invoke_endpoint(self, **kwargs):
            return {}

    monkeypatch.setattr(SageMakerAdapter, "_build_client", lambda self: EmptyBodyClient())
    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m")
    with pytest.raises(LLMResponseError, match="body"):
        adapter.complete(REQ)


def test_response_body_as_raw_bytes_accepted():
    class BytesClient:
        def invoke_endpoint(self, **kwargs):
            return {"Body": ENVELOPE_OK}

    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=BytesClient())
    response = adapter.complete(REQ)
    assert response.rationale == "made bucket private"


def test_response_body_as_string_accepted():
    class StrClient:
        def invoke_endpoint(self, **kwargs):
            return {"Body": ENVELOPE_OK.decode()}

    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_client=StrClient())
    response = adapter.complete(REQ)
    assert response.patch is not None
