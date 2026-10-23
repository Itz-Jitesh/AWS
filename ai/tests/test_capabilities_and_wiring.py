"""Unit tests for factory selection, /capabilities reporting, env wiring of
Worker/Audit HTTP clients, and consistent API error mapping.

All AWS interactions are mocked or absent; no live endpoint is contacted.
"""

import pytest
from fastapi.testclient import TestClient

from planproof_ai.app import create_app
from planproof_ai.clients import HttpAuditClient, HttpWorkerClient
from planproof_ai.config import AIConfig
from planproof_ai.errors import (
    AuditError,
    LLMResponseError,
    LLMUnavailableError,
    ModelNotConfiguredError,
    WorkerUnavailableError,
)
from planproof_ai.llm.base import LLMRequest
from planproof_ai.llm.factory import create_adapter, resolve_backend
from planproof_ai.llm.mock import MockLLMAdapter
from planproof_ai.llm.sagemaker import SageMakerAdapter
from planproof_ai.testing import MockAuditClient, MockWorkerClient


def test_explicit_mock_backend_selected():
    adapter = create_adapter(AIConfig(model_backend="mock"))
    assert isinstance(adapter, MockLLMAdapter)


def test_explicit_sagemaker_backend_selected():
    adapter = create_adapter(
        AIConfig(model_backend="sagemaker", sagemaker_endpoint_name="ep")
    )
    assert isinstance(adapter, SageMakerAdapter)
    assert adapter.endpoint_name == "ep"
    assert adapter.endpoint_configured is True


def test_endpoint_env_implies_sagemaker_when_backend_empty():
    config = AIConfig.from_env({"SAGEMAKER_ENDPOINT_NAME": "ep"})
    assert resolve_backend(config) == "sagemaker"
    assert isinstance(create_adapter(config), SageMakerAdapter)


def test_empty_backend_without_endpoint_is_mock():
    config = AIConfig.from_env({})
    assert resolve_backend(config) == "mock"


def test_explicit_mock_wins_over_endpoint_env():
    config = AIConfig.from_env({"MODEL_BACKEND": "mock", "SAGEMAKER_ENDPOINT_NAME": "ep"})
    assert resolve_backend(config) == "mock"
    assert isinstance(create_adapter(config), MockLLMAdapter)


def test_unknown_backend_fails_closed():
    with pytest.raises(ModelNotConfiguredError, match="bedrock"):
        create_adapter(AIConfig(model_backend="bedrock"))


def test_sagemaker_backend_without_endpoint_builds_but_fails_closed_on_use():
    adapter = create_adapter(AIConfig(model_backend="sagemaker", sagemaker_endpoint_name=""))
    assert isinstance(adapter, SageMakerAdapter)
    assert adapter.endpoint_configured is False
    with pytest.raises(ModelNotConfiguredError):
        adapter.complete(LLMRequest(prompt="p"))


def test_sagemaker_env_configuration_maps_to_adapter():
    config = AIConfig.from_env(
        {
            "MODEL_BACKEND": "sagemaker",
            "SAGEMAKER_ENDPOINT_NAME": "gemma-endpoint",
            "SAGEMAKER_REGION": "eu-west-1",
            "SAGEMAKER_PAYLOAD_MODE": "hf",
            "MODEL_ID": "google/gemma-4-E4B-it",
        }
    )
    adapter = create_adapter(config)
    assert adapter.endpoint_name == "gemma-endpoint"
    assert adapter.region == "eu-west-1"
    assert adapter.payload_mode == "hf"
    assert adapter.model_id == "google/gemma-4-E4B-it"


def test_unknown_payload_mode_env_fails_at_adapter_construction():
    config = AIConfig.from_env(
        {"MODEL_BACKEND": "sagemaker", "SAGEMAKER_ENDPOINT_NAME": "ep", "SAGEMAKER_PAYLOAD_MODE": "bogus"}
    )
    with pytest.raises(ValueError, match="payload mode"):
        create_adapter(config)


def test_capabilities_reports_mock_model_without_secrets():
    config = AIConfig.from_env({})
    app = create_app(llm=MockLLMAdapter([]), config=config)
    resp = TestClient(app).get("/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model"]["backend"] == "mock"
    assert body["model"]["adapter"] == "MockLLMAdapter"
    assert body["model"]["requires_live_endpoint"] is False
    assert body["model"]["endpoint_configured"] is False
    assert body["model"]["endpoint_name"] is None
    assert body["model"]["payload_mode"] is None
    assert body["worker"]["mode"] == "mock"
    assert body["audit"]["mode"] == "mock"
    assert body["repair_max_attempts"] == 3
    raw = resp.text
    assert "AKIA" not in raw
    assert "secret" not in raw.lower()
    assert "aws_access_key" not in raw.lower()


def test_capabilities_reports_sagemaker_live_configuration():
    config = AIConfig.from_env(
        {
            "MODEL_BACKEND": "sagemaker",
            "SAGEMAKER_ENDPOINT_NAME": "gemma-endpoint",
            "MODEL_ID": "google/gemma-4-E4B-it",
            "WORKER_BASE_URL": "http://worker.internal:8081",
            "AUDIT_BASE_URL": "http://audit.internal:8080",
        }
    )
    app = create_app(config=config)
    client = TestClient(app)
    caps = client.get("/capabilities").json()
    assert caps["model"]["backend"] == "sagemaker"
    assert caps["model"]["adapter"] == "SageMakerAdapter"
    assert caps["model"]["requires_live_endpoint"] is True
    assert caps["model"]["endpoint_configured"] is True
    assert caps["model"]["endpoint_name"] == "gemma-endpoint"
    assert caps["model"]["payload_mode"] == "planproof"
    assert caps["model"]["model_id"] == "google/gemma-4-E4B-it"
    assert caps["worker"] == {"mode": "http", "base_url": "http://worker.internal:8081"}
    assert caps["audit"] == {"mode": "http", "base_url": "http://audit.internal:8080"}

    health = client.get("/health").json()
    assert health["model_backend"] == "sagemaker"


def test_capabilities_never_echoes_aws_credentials():
    config = AIConfig.from_env(
        {
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "SAGEMAKER_ENDPOINT_NAME": "ep",
        }
    )
    app = create_app(config=config)
    raw = TestClient(app).get("/capabilities").text
    assert "AKIAIOSFODNN7EXAMPLE" not in raw
    assert "wJalrXUtnFEMI" not in raw


def test_worker_audit_http_wiring_from_env():
    config = AIConfig.from_env(
        {"WORKER_BASE_URL": "http://worker:8081", "AUDIT_BASE_URL": "http://audit:8080"}
    )
    app = create_app(config=config)
    assert isinstance(app.state.worker, HttpWorkerClient)
    assert isinstance(app.state.audit, HttpAuditClient)
    assert app.state.worker.base_url.rstrip("/") == "http://worker:8081"
    assert app.state.audit.base_url.rstrip("/") == "http://audit:8080"


def test_worker_audit_default_to_mock_without_env():
    config = AIConfig.from_env({})
    app = create_app(config=config)
    assert isinstance(app.state.worker, MockWorkerClient)
    assert isinstance(app.state.audit, MockAuditClient)


def test_worker_audit_injected_clients_take_precedence_over_env():
    config = AIConfig.from_env(
        {"WORKER_BASE_URL": "http://worker:8081", "AUDIT_BASE_URL": "http://audit:8080"}
    )
    worker = MockWorkerClient()
    audit = MockAuditClient()
    app = create_app(config=config, worker=worker, audit=audit)
    assert app.state.worker is worker
    assert app.state.audit is audit


class RaisingLLM(MockLLMAdapter):
    def __init__(self, exc):
        super().__init__([])
        self._exc = exc

    def complete(self, request):
        raise self._exc


def client_for(llm) -> TestClient:
    return TestClient(create_app(llm=llm, config=AIConfig()))


def test_requirements_llm_unavailable_maps_to_503():
    resp = client_for(RaisingLLM(LLMUnavailableError("down"))).post(
        "/tasks/t1/requirements", json={"goal": "x"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "llm_unavailable"


def test_requirements_llm_response_error_maps_to_502():
    resp = client_for(RaisingLLM(LLMResponseError("bad json"))).post(
        "/tasks/t1/requirements", json={"goal": "x"}
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "llm_response_invalid"


def test_patch_llm_unavailable_maps_to_503():
    resp = client_for(RaisingLLM(LLMUnavailableError("down"))).post(
        "/tasks/t1/patch", json={"workspace": "ws", "goal": "x"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "llm_unavailable"


def test_patch_llm_response_error_maps_to_502():
    resp = client_for(RaisingLLM(LLMResponseError("bad json"))).post(
        "/tasks/t1/patch", json={"workspace": "ws", "goal": "x"}
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "llm_response_invalid"


def test_repair_worker_unavailable_maps_to_503(monkeypatch):
    def boom(*args, **kwargs):
        raise WorkerUnavailableError("worker down")

    monkeypatch.setattr("planproof_ai.app.repair_loop", boom)
    resp = client_for(MockLLMAdapter([])).post(
        "/tasks/t1/repair", json={"workspace": "ws", "goal": "x"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "worker_unavailable"


def test_repair_audit_error_maps_to_503(monkeypatch):
    def boom(*args, **kwargs):
        raise AuditError("audit down")

    monkeypatch.setattr("planproof_ai.app.repair_loop", boom)
    resp = client_for(MockLLMAdapter([])).post(
        "/tasks/t1/repair", json={"workspace": "ws", "goal": "x"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "audit_error"


def test_repair_llm_unavailable_maps_to_503(monkeypatch):
    def boom(*args, **kwargs):
        raise LLMUnavailableError("model down")

    monkeypatch.setattr("planproof_ai.app.repair_loop", boom)
    resp = client_for(MockLLMAdapter([])).post(
        "/tasks/t1/repair", json={"workspace": "ws", "goal": "x"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "llm_unavailable"
