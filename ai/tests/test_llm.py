import json
import urllib.error

import pytest

from planproof_ai.config import AIConfig
from planproof_ai.errors import LLMResponseError, LLMUnavailableError, ModelNotConfiguredError
from planproof_ai.llm.base import LLMRequest
from planproof_ai.llm.factory import create_adapter
from planproof_ai.llm.mock import MockLLMAdapter
from planproof_ai.llm.ollama import OllamaAdapter
from planproof_ai.llm.sagemaker import SageMakerAdapter

REQ = LLMRequest(prompt="prompt", diagnostics="diag", max_tokens=128)


def test_mock_returns_preset_responses_in_order():
    from planproof_ai.llm.base import LLMResponse

    adapter = MockLLMAdapter([
        LLMResponse(patch=None, rationale="first", model_id="m1"),
        LLMResponse(patch=None, rationale="second", model_id="m1"),
    ])
    assert adapter.complete(REQ).rationale == "first"
    assert adapter.complete(REQ).rationale == "second"


def test_mock_records_requests_and_repeats_last():
    from planproof_ai.llm.base import LLMResponse

    adapter = MockLLMAdapter([LLMResponse(patch=None, rationale="only", model_id="m")])
    adapter.complete(REQ)
    adapter.complete(LLMRequest(prompt="second"))
    assert len(adapter.requests) == 2
    assert adapter.requests[1].prompt == "second"
    assert adapter.complete(REQ).rationale == "only"


def test_mock_without_responses_raises():
    adapter = MockLLMAdapter([])
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_ollama_adapter_composes_request():
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"response": "hello from model", "done": True, "model": "gemma3"}

    adapter = OllamaAdapter(base_url="http://localhost:11434/", model="gemma3", post_json=fake_post)
    response = adapter.complete(REQ)
    assert response.rationale == "hello from model"
    assert response.model_id == "ollama/gemma3"
    assert response.finish_reason == "stop"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"]["num_predict"] == 128
    assert "Diagnostics (redacted):\ndiag" in captured["payload"]["prompt"]


def test_ollama_network_error_becomes_llm_unavailable():
    def failing_post(url, payload):
        raise urllib.error.URLError("connection refused")

    adapter = OllamaAdapter(post_json=failing_post)
    with pytest.raises(LLMUnavailableError):
        adapter.complete(REQ)


def test_ollama_bad_payload_raises():
    adapter = OllamaAdapter(post_json=lambda url, payload: {"nope": 1})
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_sagemaker_unconfigured_raises():
    adapter = SageMakerAdapter(endpoint_name="", model_id="gemma-x")
    with pytest.raises(ModelNotConfiguredError) as excinfo:
        adapter.complete(REQ)
    assert "validate" in str(excinfo.value)


def test_sagemaker_endpoint_without_invoke_raises():
    adapter = SageMakerAdapter(endpoint_name="my-endpoint")
    with pytest.raises(ModelNotConfiguredError):
        adapter.complete(REQ)


def test_sagemaker_with_injected_invoke_parses_response():
    def invoke(payload: str) -> str:
        data = json.loads(payload)
        assert data["prompt"] == "prompt"
        assert data["max_tokens"] == 128
        return json.dumps(
            {"patch": "--- a/main.tf\n+++ b/main.tf\n", "rationale": "done", "model_id": "sm-1", "finish_reason": "stop"}
        )

    adapter = SageMakerAdapter(endpoint_name="ep", model_id="m", invoke_fn=invoke)
    response = adapter.complete(REQ)
    assert response.patch.startswith("--- a/main.tf")
    assert response.model_id == "sm-1"


def test_sagemaker_bad_payload_raises():
    adapter = SageMakerAdapter(endpoint_name="ep", invoke_fn=lambda payload: "not-json")
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_sagemaker_missing_rationale_raises():
    adapter = SageMakerAdapter(endpoint_name="ep", invoke_fn=lambda payload: json.dumps({"foo": 1}))
    with pytest.raises(LLMResponseError):
        adapter.complete(REQ)


def test_factory_backends():
    assert isinstance(create_adapter(AIConfig(model_backend="mock")), MockLLMAdapter)
    ollama = create_adapter(AIConfig(model_backend="ollama", model_id="gemma3"))
    assert isinstance(ollama, OllamaAdapter)
    assert ollama.model == "gemma3"
    sm = create_adapter(AIConfig(model_backend="sagemaker", sagemaker_endpoint_name="ep"))
    assert isinstance(sm, SageMakerAdapter)
    assert sm.endpoint_name == "ep"
