"""Checkov adapter tests: every failure mode is UnableToVerify, never Passed."""

from __future__ import annotations

import pytest

from audit.checkov import run_checkov
from audit.contracts import validate

from .conftest import FIXTURES, make_executable


def _assert_all_contract_valid(findings: list[dict]) -> None:
    assert findings, "expected at least one finding record"
    for finding in findings:
        validate(finding, "finding")


def test_missing_binary_reports_unable_to_verify(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", "/definitely/empty")
    [finding] = run_checkov(tmp_path)
    validate(finding, "finding")
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_source"] == "custom"
    assert finding["rule_id"] == "scanner.checkov.binary_missing"
    assert "not found" in finding["evidence"]
    assert finding["status"] != "Passed"


def test_bad_env_override_reports_unable_to_verify(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("PLANPROOF_CHECKOV_BIN", "/no/such/checkov")
    [finding] = run_checkov(tmp_path)
    assert finding["status"] == "UnableToVerify"
    assert "PLANPROOF_CHECKOV_BIN" in finding["evidence"]


def test_missing_workspace_reports_unable_to_verify(tmp_bin) -> None:
    fake = make_executable(tmp_bin, "fake_checkov", "#!/bin/sh\nexit 0\n")
    [finding] = run_checkov("/no/such/workspace", executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.checkov.workspace_missing"


def test_successful_scan_normalizes_results(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        f'#!/bin/sh\ncat "{FIXTURES / "checkov_results_sample.json"}"\n',
    )
    findings = run_checkov(tmp_path, executable=str(fake))
    _assert_all_contract_valid(findings)
    by_key = {(f["rule_id"], f["status"]) for f in findings}
    assert ("CKV_AWS_20", "Failed") in by_key
    assert ("CKV_AWS_18", "Passed") in by_key
    assert ("CKV_AWS_52", "Skipped") in by_key
    failed = [f for f in findings if f["status"] == "Failed"]
    public = next(f for f in failed if f["rule_id"] == "CKV_AWS_20")
    assert public["severity"] == "critical"
    assert public["resource_address"] == "aws_s3_bucket.public_data"
    assert public["line_start"] == 1
    assert "public READ" in public["evidence"]
    weird = next(f for f in findings if f["rule_id"] == "CKV_AWS_999")
    assert weird["severity"] == "unknown"
    assert all(f["status"] != "UnableToVerify" for f in findings)


def test_argv_is_fixed_argument_array(tmp_bin, tmp_path) -> None:
    args_file = tmp_bin / "args.txt"
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$(dirname "$0")/args.txt"\n'
        f'cat "{FIXTURES / "checkov_results_sample.json"}"\n',
    )
    run_checkov(tmp_path, executable=str(fake))
    args = args_file.read_text().splitlines()
    assert args[0] == "-d"
    assert str(tmp_path) in args
    assert "-o" in args and "json" in args
    assert "--quiet" in args
    assert not any("&&" in arg or ";" in arg for arg in args)


def test_results_file_fallback_when_stdout_empty(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        '#!/bin/sh\n'
        f'cp "{FIXTURES / "checkov_results_sample.json"}" results_json.json\n',
    )
    findings = run_checkov(tmp_path, executable=str(fake))
    _assert_all_contract_valid(findings)
    assert any(f["status"] == "Failed" for f in findings)


def test_crash_with_secret_on_stderr_is_unable_to_verify_redacted(
    tmp_bin, tmp_path
) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        '#!/bin/sh\necho "Traceback: boom secret_access_key = hunter2hunter2" >&2\nexit 2\n',
    )
    [finding] = run_checkov(tmp_path, executable=str(fake))
    validate(finding, "finding")
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.checkov.malformed_output"
    assert finding["rule_source"] == "custom"
    assert "hunter2hunter2" not in finding["evidence"]
    assert "[REDACTED]" in finding["evidence"]
    assert "exit code 2" in finding["evidence"]


def test_timeout_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_checkov", "#!/bin/sh\nsleep 30\nexit 0\n")
    [finding] = run_checkov(tmp_path, executable=str(fake), timeout_sec=0.4)
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.checkov.timeout"
    assert "time limit" in finding["evidence"]


def test_malformed_stdout_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_checkov", '#!/bin/sh\necho "not json"\n')
    [finding] = run_checkov(tmp_path, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.checkov.malformed_output"


def test_non_object_json_is_unable_to_verify(tmp_bin, tmp_path) -> None:
    fake = make_executable(tmp_bin, "fake_checkov", '#!/bin/sh\necho \'["array"]\'\n')
    [finding] = run_checkov(tmp_path, executable=str(fake))
    assert finding["status"] == "UnableToVerify"


def test_empty_results_are_not_configured_not_passed(tmp_bin, tmp_path) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        f'#!/bin/sh\ncat "{FIXTURES / "checkov_results_empty.json"}"\n',
    )
    [finding] = run_checkov(tmp_path, executable=str(fake))
    validate(finding, "finding")
    assert finding["status"] == "NotConfigured"
    assert finding["rule_id"] == "scanner.checkov.no_results"
    assert finding["status"] != "Passed"


def test_non_executable_override_is_unable_to_verify(tmp_path) -> None:
    broken = tmp_path / "not_executable"
    broken.write_text("#!/bin/sh\nexit 0\n")
    broken.chmod(0o644)
    [finding] = run_checkov(tmp_path, executable=str(broken))
    assert finding["status"] == "UnableToVerify"
    assert "not executable" in finding["evidence"]


def test_entry_without_check_id_makes_whole_scan_unable_to_verify(
    tmp_bin, tmp_path
) -> None:
    fake = make_executable(
        tmp_bin,
        "fake_checkov",
        '#!/bin/sh\necho \'{"results": {"failed_checks": [{"resource": "x"}], "passed_checks": [], "skipped_checks": []}}\'\n',
    )
    [finding] = run_checkov(tmp_path, executable=str(fake))
    assert finding["status"] == "UnableToVerify"
    assert finding["rule_id"] == "scanner.checkov.malformed_output"
