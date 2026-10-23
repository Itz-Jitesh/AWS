from __future__ import annotations

from conftest import INVALID_MAIN_TF, VALID_MAIN_TF, b64, build_zip_bytes


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


def _status_by_name(runs: list[dict]) -> dict[str, dict]:
    return {run["check_id"].split(":", 1)[1]: run for run in runs}


def test_full_check_suite_passes_on_valid_repo(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    response = client.post(
        "/check",
        json={"task_id": task_id, "checks": ["fmt", "init", "validate", "plan", "show_json"]},
    )
    assert response.status_code == 200
    runs = response.json()["runs"]
    by_name = _status_by_name(runs)
    assert list(by_name) == ["fmt", "init", "validate", "plan", "show_json"]
    for name, run in by_name.items():
        assert run["status"] == "Passed", f"{name}: {run}"
        assert run["schema_version"] == "1.0.0"
        assert run["exit_code"] == 0
        assert run["tool"] == "terraform"
        assert run["tool_version"] == "Terraform 1.9.5 (fake)"
        assert run["duration_ms"] >= 0
        assert run["stdout_artifact"] and run["stderr_artifact"]


def test_invalid_terraform_returns_failed_validate(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client, INVALID_MAIN_TF)
    response = client.post(
        "/check", json={"task_id": task_id, "checks": ["fmt", "validate"]}
    )
    assert response.status_code == 200
    by_name = _status_by_name(response.json()["runs"])
    assert by_name["validate"]["status"] == "Failed"
    assert by_name["validate"]["exit_code"] != 0
    assert by_name["validate"]["status"] != "Passed"


def test_fmt_failure_reports_failed(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client, VALID_MAIN_TF + "\n# BADFMT\n")
    response = client.post("/check", json={"task_id": task_id, "checks": ["fmt"]})
    by_name = _status_by_name(response.json()["runs"])
    assert by_name["fmt"]["status"] == "Failed"
    assert by_name["fmt"]["exit_code"] == 1


def test_missing_terraform_binary_reports_unable_to_verify(env):
    client = env.client()
    task_id = _ingest(client)
    response = client.post(
        "/check", json={"task_id": task_id, "checks": ["fmt", "validate"]}
    )
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert runs
    by_name = _status_by_name(runs)
    for run in runs:
        assert run["status"] == "UnableToVerify"
        assert run["exit_code"] is None
        assert run["tool_version"] is None
    assert any(
        "not available on PATH" in item for item in by_name["fmt"]["limitations"]
    )
    assert any(
        "prerequisite" in item for item in by_name["validate"]["limitations"]
    )
    assert all(run["status"] != "Passed" for run in runs)


def test_command_timeout_never_reports_passed(env):
    env.install_terraform(behavior="hang")
    client = env.client(check_timeout_s=1)
    task_id = _ingest(client)
    response = client.post("/check", json={"task_id": task_id, "checks": ["fmt"]})
    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["status"] == "UnableToVerify"
    assert run["exit_code"] is None
    assert "timed out" in run["summary"]
    assert any("timed out" in item for item in run["limitations"])
    assert 900 <= run["duration_ms"] < 20000


def test_tool_crash_never_reports_passed(env):
    env.install_terraform(behavior="crash")
    client = env.client()
    task_id = _ingest(client)
    response = client.post("/check", json={"task_id": task_id, "checks": ["fmt"]})
    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["status"] == "UnableToVerify"
    assert run["exit_code"] is None
    assert "signal" in run["summary"].lower()


def test_implicit_prerequisite_init_runs_before_validate(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client)
    response = client.post("/check", json={"task_id": task_id, "checks": ["validate"]})
    assert response.status_code == 200
    names = [run["check_id"].split(":", 1)[1] for run in response.json()["runs"]]
    assert names == ["init", "validate"]
    assert response.json()["runs"][1]["status"] == "Passed"


def test_failed_prerequisite_blocks_dependent_check(env):
    env.install_terraform()
    client = env.client()
    task_id = _ingest(client, VALID_MAIN_TF + "\n# BADINIT\n")
    response = client.post("/check", json={"task_id": task_id, "checks": ["validate"]})
    by_name = _status_by_name(response.json()["runs"])
    assert by_name["init"]["status"] == "Failed"
    assert by_name["validate"]["status"] == "UnableToVerify"
    assert any(
        "prerequisite" in item and "init" in item
        for item in by_name["validate"]["limitations"]
    )


def test_show_json_without_plan_artifact_reports_unable_to_verify(env):
    env.install_terraform(behavior="plan_nowrite")
    client = env.client()
    task_id = _ingest(client)
    response = client.post(
        "/check", json={"task_id": task_id, "checks": ["show_json"]}
    )
    by_name = _status_by_name(response.json()["runs"])
    assert by_name["plan"]["status"] == "Passed"
    assert by_name["show_json"]["status"] == "UnableToVerify"
    assert any(
        "tfplan" in item for item in by_name["show_json"]["limitations"]
    )


def test_child_environment_is_allowlisted(env):
    env.install_terraform()
    env.monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "parent-secret-value-xyz123")
    env.monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAparentparentparent")
    client = env.client()
    task_id = _ingest(client)
    response = client.post("/check", json={"task_id": task_id, "checks": ["fmt"]})
    assert response.status_code == 200
    dump = env.data_dir / task_id / "repo" / "envdump.json"
    assert dump.is_file()
    child_env = dump.read_text()
    assert "parent-secret-value-xyz123" not in child_env
    assert "AKIAparentparentparent" not in child_env
    assert '"TF_IN_AUTOMATION": "1"' in child_env
    assert '"GIT_TERMINAL_PROMPT": "0"' in child_env
    assert '"PATH"' in child_env


def test_check_unknown_task_returns_404(env):
    env.install_terraform()
    client = env.client()
    response = client.post("/check", json={"task_id": "a" * 32, "checks": ["fmt"]})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TASK_NOT_FOUND"


def test_check_duplicate_checks_rejected(env):
    client = env.client()
    response = client.post(
        "/check", json={"task_id": "a" * 32, "checks": ["fmt", "fmt"]}
    )
    assert response.status_code == 422


def test_check_unknown_check_type_rejected(env):
    client = env.client()
    response = client.post(
        "/check", json={"task_id": "a" * 32, "checks": ["apply"]}
    )
    assert response.status_code == 422
