from __future__ import annotations

import pytest
from jsonschema import ValidationError
from pydantic import ValidationError as PydanticValidationError

from app.contracts import SCHEMA_DIR, checkrun_schema, validate_checkrun_payload
from app.models import CheckRun


def _valid_run() -> dict:
    return {
        "schema_version": "1.0.0",
        "check_id": "abc123:fmt",
        "tool": "terraform",
        "status": "Passed",
        "started_at": "2026-10-23T10:00:00Z",
        "duration_ms": 12,
        "summary": "ok",
        "exit_code": 0,
        "tool_version": "Terraform 1.9.5",
        "stdout_artifact": "abc/artifacts/fmt.stdout.log",
        "stderr_artifact": "abc/artifacts/fmt.stderr.log",
        "limitations": [],
    }


def test_contract_schema_file_exists():
    assert (SCHEMA_DIR / "checkrun.schema.json").is_file()


def test_valid_payload_passes_schema_validation():
    validate_checkrun_payload(_valid_run())


def test_invalid_status_fails_schema_validation():
    payload = _valid_run()
    payload["status"] = "Success"
    with pytest.raises(ValidationError):
        validate_checkrun_payload(payload)


def test_missing_required_field_fails_schema_validation():
    payload = _valid_run()
    del payload["summary"]
    with pytest.raises(ValidationError):
        validate_checkrun_payload(payload)


def test_extra_field_fails_schema_validation():
    payload = _valid_run()
    payload["secure"] = True
    with pytest.raises(ValidationError):
        validate_checkrun_payload(payload)


def test_bad_timestamp_fails_schema_validation():
    payload = _valid_run()
    payload["started_at"] = "not-a-timestamp"
    with pytest.raises(ValidationError):
        validate_checkrun_payload(payload)


def test_pydantic_model_forbids_extra_fields():
    with pytest.raises(PydanticValidationError):
        CheckRun(
            check_id="x",
            tool="terraform",
            status="Passed",
            started_at="2026-10-23T10:00:00Z",
            duration_ms=1,
            summary="ok",
            secure=True,
        )


def test_loaded_schema_matches_frozen_version():
    assert checkrun_schema()["properties"]["schema_version"]["const"] == "1.0.0"
    assert checkrun_schema()["additionalProperties"] is False


def test_live_check_runs_validate_against_contract(env):
    from conftest import VALID_MAIN_TF, b64, build_zip_bytes

    env.install_terraform()
    client = env.client()
    ingest = client.post(
        "/ingest",
        json={
            "source_type": "zip",
            "filename": "repo.zip",
            "zip_base64": b64(build_zip_bytes([("main.tf", VALID_MAIN_TF.encode())])),
        },
    )
    task_id = ingest.json()["task_id"]
    response = client.post(
        "/check",
        json={"task_id": task_id, "checks": ["fmt", "init", "validate", "plan", "show_json"]},
    )
    runs = response.json()["runs"]
    assert runs
    for run in runs:
        validate_checkrun_payload(run)
