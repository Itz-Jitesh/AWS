import json

import httpx
import pytest

from planproof_ai.clients import HttpAuditClient, HttpWorkerClient
from planproof_ai.errors import AuditError, WorkerUnavailableError
from planproof_ai.testing import make_check, make_requirement


def worker_client(handler) -> HttpWorkerClient:
    return HttpWorkerClient("http://worker.test", transport=httpx.MockTransport(handler))


def test_worker_check_suite_parses_contract():
    check_json = make_check("fmt", "Passed", summary="ok").model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/check"
        body = json.loads(request.content)
        assert body == {"workspace": "/ws", "task_id": "t1"}
        return httpx.Response(200, json={"checks": [check_json]})

    client = worker_client(handler)
    checks = client.run_check_suite("/ws", "t1")
    assert len(checks) == 1
    assert checks[0].check_id == "fmt"
    assert checks[0].status.value == "Passed"


def test_worker_http_error_becomes_unavailable():
    client = worker_client(lambda request: httpx.Response(500, json={}))
    with pytest.raises(WorkerUnavailableError):
        client.run_check_suite("/ws", "t1")


def test_worker_transport_error_becomes_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = worker_client(handler)
    with pytest.raises(WorkerUnavailableError):
        client.run_check_suite("/ws", "t1")


def test_worker_missing_field_becomes_unavailable():
    client = worker_client(lambda request: httpx.Response(200, json={"checks": {}}))
    with pytest.raises(WorkerUnavailableError):
        client.run_check_suite("/ws", "t1")


def test_worker_invalid_checkrun_becomes_unavailable():
    bad = make_check("fmt", "Passed").model_dump(mode="json")
    bad["status"] = "Secure"
    client = worker_client(
        lambda request: httpx.Response(200, json={"checks": [bad]})
    )
    with pytest.raises(WorkerUnavailableError):
        client.run_check_suite("/ws", "t1")


def test_worker_capture_plan_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/capture"
        return httpx.Response(200, json={"plan_json": {"format_version": "1.2"}})

    client = worker_client(handler)
    plan = client.capture_plan_json("/ws", "t1")
    assert plan == {"format_version": "1.2"}


def test_worker_capture_error():
    client = worker_client(lambda request: httpx.Response(503, json={}))
    with pytest.raises(WorkerUnavailableError):
        client.capture_plan_json("/ws", "t1")


def audit_client(handler) -> HttpAuditClient:
    return HttpAuditClient("http://audit.test", transport=httpx.MockTransport(handler))


def test_audit_intent_parses_requirements():
    req_json = make_requirement("bucket private", status="Satisfied").model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/intent"
        body = json.loads(request.content)
        assert body["diff"] == "--- a/main.tf\n"
        assert body["plan_summary"] is None
        return httpx.Response(200, json={"requirements": [req_json]})

    client = audit_client(handler)
    reqs = client.check_intent([make_requirement("bucket private")], "--- a/main.tf\n", None)
    assert reqs[0].status.value == "Satisfied"


def test_audit_intent_error_status():
    client = audit_client(lambda request: httpx.Response(500, json={}))
    with pytest.raises(AuditError):
        client.check_intent([make_requirement("x")], "", None)


def test_audit_intent_invalid_requirement():
    client = audit_client(
        lambda request: httpx.Response(200, json={"requirements": [{"bad": 1}]})
    )
    with pytest.raises(AuditError):
        client.check_intent([make_requirement("x")], "", None)


def test_audit_classify_plan():
    summary = {
        "schema_version": "1.0.0",
        "plan_digest": "b" * 64,
        "create": 0,
        "update": 0,
        "replace": 0,
        "destroy": 1,
        "destructive_actions": [],
        "has_changes": True,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/plan/classify"
        body = json.loads(request.content)
        assert body["plan_json"]["format_version"] == "1.2"
        return httpx.Response(200, json={"plan_summary": summary})

    client = audit_client(handler)
    result = client.classify_plan("/ws", {"format_version": "1.2"})
    assert result.destroy == 1


def test_audit_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = audit_client(handler)
    with pytest.raises(AuditError):
        client.classify_plan("/ws", {})
