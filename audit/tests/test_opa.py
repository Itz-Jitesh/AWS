"""OPA adapter tests, including a real-OPA integration test when available."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.contracts import validate
from audit.opa import QUERY, run_opa

from .conftest import FIXTURES, load_fixture, make_executable

_REAL_OPA = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "opa"


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.tf").write_text('resource "aws_s3_bucket" "example" {}\n')
    return ws


def test_missing_binary_reports_unable_to_verify(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", "/definitely/empty")
    [finding] = run_opa(_workspace(tmp_path), {"resource_changes": []})
    validate(finding, "finding")
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.binary_missing"
    assert finding["rule_source"] == "custom"


def test_missing_workspace_reports_unable_to_verify(tmp_bin) -> None:
    fake = make_executable(tmp_bin, "fake_opa", "#!/bin/sh\nexit 0\n")
    [finding] = run_opa("/no/such/workspace", {}, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.workspace_missing"


@pytest.mark.parametrize("bad_plan", ["not a dict", None, ["list"], 7])
def test_invalid_plan_input_reports_unable_to_verify(tmp_bin, tmp_path, bad_plan) -> None:
    fake = make_executable(tmp_bin, "fake_opa", "#!/bin/sh\nexit 0\n")
    [finding] = run_opa(_workspace(tmp_path), bad_plan, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.invalid_plan"


def test_missing_policy_directory_reports_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_opa", "#!/bin/sh\nexit 0\n")
    [finding] = run_opa(
        _workspace(tmp_path),
        {"resource_changes": []},
        executable=str(fake),
        policies_dir=tmp_path / "no_policies",
    )
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.policy_unavailable"


def test_empty_policy_directory_reports_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_opa", "#!/bin/sh\nexit 0\n")
    empty = tmp_path / "policies"
    empty.mkdir()
    [finding] = run_opa(
        _workspace(tmp_path),
        {"resource_changes": []},
        executable=str(fake),
        policies_dir=empty,
    )
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.policy_unavailable"


def test_successful_eval_normalizes_denials(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_opa",
        f'#!/bin/sh\ncat "{FIXTURES / "opa_eval_result.json"}"\n',
    )
    findings = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert len(findings) == 3
    for finding in findings:
        validate(finding, "finding")
        assert finding["rule_source"] == "opa"
        assert finding["status"] == "Failed"
        assert finding["severity"] == "high"
        assert finding["evidence"]
    rules = {f["rule_id"] for f in findings}
    assert rules == {
        "TF_S3_PUBLIC_ACL",
        "TF_IAM_WILDCARD_RESOURCE",
        "TF_PLAN_DESTRUCTIVE_ACTION",
    }
    destructive = next(f for f in findings if f["rule_id"] == "TF_PLAN_DESTRUCTIVE_ACTION")
    assert destructive["resource_address"] == "aws_s3_bucket.public_data"


def test_argv_targets_deny_set(tmp_bin, tmp_path) -> None:
    args_file = tmp_bin / "args.txt"
    fake = make_executable(
        tmp_bin,
        "fake_opa",
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$(dirname "$0")/args.txt"\n'
        f'cat "{FIXTURES / "opa_eval_result.json"}"\n',
    )
    run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    args = args_file.read_text().splitlines()
    assert args[0] == "eval"
    assert QUERY in args
    assert "-d" in args
    assert "-i" in args
    assert any(arg.endswith(".rego") or "policies" in arg for arg in args)


def test_empty_deny_set_is_clean_success(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_opa",
        '#!/bin/sh\necho \'{"result":[{"expressions":[{"value":[]}]}]}\'\n',
    )
    findings = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert findings == []


def test_eval_failure_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_opa",
        '#!/bin/sh\necho "1 error occurred: rego_compile_error: bad token" >&2\nexit 1\n',
    )
    [finding] = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.eval_failed"
    assert "rego_compile_error" in finding["evidence"]


def test_malformed_output_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_opa", '#!/bin/sh\necho "html error page"\n')
    [finding] = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.malformed_output"


def test_undefined_query_shape_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_opa", '#!/bin/sh\necho \'{"result":[]}\'\n')
    [finding] = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert finding["status"] == "UnableToVerify"


def test_denial_without_message_makes_scan_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_opa",
        '#!/bin/sh\necho \'{"result":[{"expressions":[{"value":[{"rule":"X","severity":"high"}]}]}]}\'\n',
    )
    [finding] = run_opa(_workspace(tmp_path), {"resource_changes": []}, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.malformed_output"


def test_timeout_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_opa", "#!/bin/sh\nsleep 30\n")
    [finding] = run_opa(
        _workspace(tmp_path), {"resource_changes": []}, executable=str(fake), timeout_sec=0.4
    )
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.opa.timeout"


@pytest.mark.skipif(not _REAL_OPA.is_file(), reason="real opa binary not available in .venv")
def test_real_opa_evaluates_bundled_policies(tmp_path) -> None:
    plan = load_fixture("plan_s3_delete_iam_update.json")
    findings = run_opa(_workspace(tmp_path), plan, executable=str(_REAL_OPA))
    assert findings, "expected real policy denials for the DoD fixture"
    for finding in findings:
        validate(finding, "finding")
        assert finding["rule_source"] == "opa"
        assert finding["status"] == "Failed"
    rules = {f["rule_id"] for f in findings}
    assert "TF_PLAN_DESTRUCTIVE_ACTION" in rules
    assert "TF_IAM_WILDCARD_RESOURCE" in rules


@pytest.mark.skipif(not _REAL_OPA.is_file(), reason="real opa binary not available in .venv")
def test_real_opa_clean_plan_returns_no_findings(tmp_path) -> None:
    findings = run_opa(
        _workspace(tmp_path), {"resource_changes": []}, executable=str(_REAL_OPA)
    )
    assert findings == []
