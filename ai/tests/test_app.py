import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from helpers import BASE_LINES, tf_response, unified_replace
from planproof_ai.app import create_app
from planproof_ai.config import AIConfig
from planproof_ai.llm.mock import MockLLMAdapter
from planproof_ai.testing import (
    MockAuditClient,
    MockWorkerClient,
    make_check,
    make_requirement,
)

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
EVIL_DIFF = "--- a/../evil.tf\n+++ b/../evil.tf\n@@ -1,1 +1,1 @@\n-x\n+y\n"


def validate_contract(name: str, payload: dict) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def build_client(llm=None, worker=None, audit=None, config=None) -> TestClient:
    app = create_app(
        llm=llm or MockLLMAdapter([]),
        worker=worker or MockWorkerClient(),
        audit=audit or MockAuditClient(),
        config=config or AIConfig(),
    )
    return TestClient(app)


def test_health():
    client = build_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_backend"] == "mock"


def test_requirements_endpoint_returns_contract_valid_unverified():
    from helpers import json_requirements_response

    llm = MockLLMAdapter([
        json_requirements_response([
            {"text": "bucket must be private", "mandatory": True, "verification": "check"},
            {"text": "optional tag", "mandatory": False},
        ])
    ])
    client = build_client(llm=llm)
    resp = client.post("/tasks/t1/requirements", json={"goal": "Make the bucket private"})
    assert resp.status_code == 200
    requirements = resp.json()["requirements"]
    assert len(requirements) == 2
    for req in requirements:
        assert req["status"] == "Unverified"
        validate_contract("requirement.schema.json", req)


def test_requirements_endpoint_rejects_empty_goal():
    client = build_client()
    resp = client.post("/tasks/t1/requirements", json={"goal": ""})
    assert resp.status_code == 422


def test_requirements_endpoint_llm_error_is_503():
    from planproof_ai.errors import LLMUnavailableError

    class Boom(LLMUnavailableError):
        pass

    class RaisingLLM(MockLLMAdapter):
        def complete(self, request):
            raise Boom("no model backend")

    client = build_client(llm=RaisingLLM([]))
    resp = client.post("/tasks/t1/requirements", json={"goal": "x"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "llm_unavailable"


def test_patch_endpoint_returns_contract_valid_patch(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    llm = MockLLMAdapter([tf_response(diff)])
    client = build_client(llm=llm)
    payload = {
        "workspace": workspace,
        "requirements": [make_requirement("bucket must be private").model_dump(mode="json")],
        "diagnostics": "",
    }
    resp = client.post("/tasks/t1/patch", json=payload)
    assert resp.status_code == 200
    patch = resp.json()["patch"]
    assert patch["files_changed"] == ["main.tf"]
    assert len(patch["base_digest"]) == 64
    validate_contract("patch.schema.json", patch)


def test_patch_endpoint_rejects_unsafe_diff(workspace):
    llm = MockLLMAdapter([tf_response(EVIL_DIFF)])
    client = build_client(llm=llm)
    payload = {
        "workspace": workspace,
        "requirements": [make_requirement("x").model_dump(mode="json")],
    }
    resp = client.post("/tasks/t1/patch", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "path_escape"


def test_patch_endpoint_requires_goal_or_requirements(workspace):
    client = build_client(llm=MockLLMAdapter([]))
    resp = client.post("/tasks/t1/patch", json={"workspace": workspace})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "bad_request"


def test_patch_endpoint_rejects_unknown_fields(workspace):
    client = build_client()
    payload = {
        "workspace": workspace,
        "requirements": [make_requirement("x").model_dump(mode="json")],
        "apply_now": True,
    }
    resp = client.post("/tasks/t1/patch", json=payload)
    assert resp.status_code == 422


def test_repair_endpoint_resolves(workspace):
    from planproof_ai.contracts import CheckStatus

    patch_diff = unified_replace(
        "main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"'
    )
    llm = MockLLMAdapter([tf_response(patch_diff)])
    worker = MockWorkerClient(
        suites=[
            [make_check("fmt", CheckStatus.FAILED, exit_code=3)],
            [make_check("fmt", CheckStatus.PASSED)],
        ]
    )

    def satisfied(requirements, diff, plan):
        return [
            make_requirement(r.text, r.requirement_id, r.mandatory, "Satisfied", ["diff evidence"])
            for r in requirements
        ]

    client = build_client(llm=llm, worker=worker, audit=MockAuditClient(intent_fn=satisfied))
    payload = {
        "workspace": workspace,
        "requirements": [make_requirement("bucket must be private").model_dump(mode="json")],
    }
    resp = client.post("/tasks/t1/repair", json=payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["stop_reason"] == "resolved"
    assert result["success"] is True
    assert len(result["attempts"]) == 1


def test_repair_endpoint_rejects_max_attempts_above_three(workspace):
    client = build_client()
    payload = {
        "workspace": workspace,
        "requirements": [make_requirement("x").model_dump(mode="json")],
        "max_attempts": 4,
    }
    resp = client.post("/tasks/t1/repair", json=payload)
    assert resp.status_code == 422
