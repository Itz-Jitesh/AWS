"""Controlled subprocess runner tests: limits, env stripping, no shell."""

from __future__ import annotations

import sys
import time

import pytest

from audit.runner import MAX_STREAM_BYTES, resolve_executable, run_argv


def test_successful_run_captures_output() -> None:
    result = run_argv([sys.executable, "-c", "print('hello')"], timeout_sec=10)
    assert result.ran
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.error is None
    assert not result.timed_out


def test_nonexistent_binary_returns_error_result() -> None:
    result = run_argv(["/definitely/not/a/binary"], timeout_sec=5)
    assert not result.ran
    assert result.error is not None
    assert result.exit_code is None


def test_timeout_is_reported_not_raised() -> None:
    start = time.monotonic()
    result = run_argv([sys.executable, "-c", "import time; time.sleep(30)"], timeout_sec=0.4)
    elapsed = time.monotonic() - start
    assert result.timed_out
    assert not result.ran
    assert result.exit_code is None
    assert elapsed < 10


def test_environment_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLANPROOF_LEAK_CANARY", "super-secret-value")
    code = "import os; print(os.environ.get('PLANPROOF_LEAK_CANARY', 'ABSENT'))"
    result = run_argv([sys.executable, "-c", code], timeout_sec=10)
    assert "ABSENT" in result.stdout
    assert "super-secret-value" not in result.stdout


def test_output_is_truncated() -> None:
    code = "import sys; sys.stdout.write('x' * 400000)"
    result = run_argv([sys.executable, "-c", code], timeout_sec=20)
    assert result.truncated
    assert len(result.stdout) < MAX_STREAM_BYTES + 200
    assert "[truncated" in result.stdout


def test_output_is_redacted() -> None:
    code = "print('token = AKIAEXAMPLEKEY1234567')"
    result = run_argv([sys.executable, "-c", code], timeout_sec=10)
    assert "AKIAEXAMPLEKEY1234567" not in result.stdout
    assert "[REDACTED]" in result.stdout


def test_stdin_input_supported() -> None:
    result = run_argv(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"],
        input_text="abc",
        timeout_sec=10,
    )
    assert result.stdout == "ABC"


def test_empty_argv_raises() -> None:
    with pytest.raises(ValueError, match="argv"):
        run_argv([])


def test_non_positive_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout"):
        run_argv([sys.executable, "-c", "pass"], timeout_sec=0)


def test_resolve_executable_env_override(monkeypatch: pytest.MonkeyPatch, tmp_bin) -> None:
    from .conftest import make_executable

    good = make_executable(tmp_bin, "fake_checkov", "#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("PLANPROOF_CHECKOV_BIN", str(good))
    path, description = resolve_executable("checkov", "PLANPROOF_CHECKOV_BIN")
    assert path == str(good)
    assert "PLANPROOF_CHECKOV_BIN" in description


def test_resolve_executable_bad_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLANPROOF_CHECKOV_BIN", "/does/not/exist")
    path, description = resolve_executable("checkov", "PLANPROOF_CHECKOV_BIN")
    assert path is None
    assert "no executable" in description


def test_resolve_executable_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/definitely/empty")
    path, description = resolve_executable("checkov", "PLANPROOF_CHECKOV_BIN")
    assert path is None
    assert "not found on PATH" in description
