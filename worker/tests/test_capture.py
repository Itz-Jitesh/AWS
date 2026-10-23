from __future__ import annotations

import hashlib

from conftest import VALID_MAIN_TF, b64, build_zip_bytes

FAKE_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
FAKE_SECRET_KEY = "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"


def _ingest(client, content: str = VALID_MAIN_TF) -> str:
    response = client.post(
        "/ingest",
        json={
            "source_type": "zip",
            "filename": "repo.zip",
            "zip_base64": b64(build_zip_bytes([("main.tf", content.encode())])),
        },
    )
    assert response.status_code == 200
    return response.json()["task_id"]


def _run_full_suite(client, task_id: str) -> None:
    response = client.post(
        "/check",
        json={"task_id": task_id, "checks": ["fmt", "init", "validate", "plan", "show_json"]},
    )
    assert response.status_code == 200
    assert all(run["status"] == "Passed" for run in response.json()["runs"])


def test_capture_unknown_task_returns_404(env):
    client = env.client()
    response = client.post("/capture", json={"task_id": "b" * 32})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TASK_NOT_FOUND"


def test_capture_invalid_task_id_rejected(env):
    client = env.client()
    response = client.post("/capture", json={"task_id": "../../etc/passwd"})
    assert response.status_code == 422


def test_capture_without_plan_reports_unavailable(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    response = client.post("/capture", json={"task_id": task_id})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "plan" in body["reason"]
    assert body["plan_digest"] is None


def test_capture_returns_redacted_plan_and_stable_digest(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    _run_full_suite(client, task_id)

    first = client.post("/capture", json={"task_id": task_id})
    assert first.status_code == 200
    body = first.json()
    assert body["available"] is True
    assert len(body["plan_digest"]) == 64
    int(body["plan_digest"], 16)
    assert FAKE_ACCESS_KEY not in first.text
    assert FAKE_SECRET_KEY not in first.text
    values = body["redacted_plan"]["planned_values"]["root_module"]["resources"][0]["values"]
    assert values["access_key_id"] == "***REDACTED***"
    assert values["secret_access_key"] == "***REDACTED***"
    assert values["acl"] == "public-read"

    second = client.post("/capture", json={"task_id": task_id})
    assert second.json()["plan_digest"] == body["plan_digest"]


def test_capture_auto_renders_plan_json_when_only_plan_ran(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    response = client.post("/check", json={"task_id": task_id, "checks": ["plan"]})
    assert response.json()["runs"][-1]["status"] == "Passed"
    capture = client.post("/capture", json={"task_id": task_id})
    assert capture.status_code == 200
    body = capture.json()
    assert body["available"] is True
    assert len(body["plan_digest"]) == 64
    assert FAKE_ACCESS_KEY not in capture.text


def test_capture_reports_missing_terraform_when_plan_exists(env):
    client = env.client()
    task_id = _ingest(client)
    plan_file = env.data_dir / task_id / "repo" / "tfplan"
    plan_file.write_bytes(b"fake-plan-binary")
    response = client.post("/capture", json={"task_id": task_id})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "not found" in body["reason"]


def test_raw_plan_is_stored_server_side_with_digest(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    _run_full_suite(client, task_id)
    capture = client.post("/capture", json={"task_id": task_id})
    digest = capture.json()["plan_digest"]

    artifacts = env.data_dir / task_id / "artifacts"
    raw_plan = artifacts / "plan.raw.json"
    assert raw_plan.is_file()
    raw_text = raw_plan.read_text()
    assert FAKE_ACCESS_KEY in raw_text
    expected = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()
    assert digest == expected
    assert oct(raw_plan.stat().st_mode)[-3:] == "600"

    stdout_artifact = env.data_dir / task_id / "artifacts" / "show_json.stdout.log"
    assert stdout_artifact.is_file()
    assert FAKE_ACCESS_KEY not in stdout_artifact.read_text()
    assert FAKE_SECRET_KEY not in stdout_artifact.read_text()
