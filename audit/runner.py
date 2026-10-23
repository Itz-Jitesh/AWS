"""Controlled subprocess execution for scanner adapters.

Callers pass fixed argument arrays; nothing here ever routes a string through
a shell. The child process gets a stripped environment, a wall-clock timeout,
bounded output, and redacted capture text so scanner failures can be reported
as evidence without leaking credentials.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .redact import redact_text

DEFAULT_TIMEOUT_SEC = 120.0
MAX_STREAM_BYTES = 200_000
_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PYTHONIOENCODING")


@dataclass(frozen=True)
class CmdResult:
    """Outcome of one controlled subprocess run."""

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None
    truncated: bool = False

    @property
    def ran(self) -> bool:
        """True when the process was executed to completion (exit code known)."""
        return self.error is None and not self.timed_out


def resolve_executable(name: str, env_var: str) -> tuple[str | None, str]:
    """Locate a scanner binary.

    Returns ``(path_or_None, description)`` where ``description`` is suitable
    for use as redacted evidence in an ``UnableToVerify`` result.
    """
    override = os.environ.get(env_var, "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return override, f"{env_var} points at {override}"
        return None, f"{env_var} is set to {override} but no executable exists there"
    found = shutil.which(name)
    if found:
        return found, f"{name} found at {found}"
    return None, f"{name} executable not found on PATH"


def run_argv(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    input_text: str | None = None,
) -> CmdResult:
    """Run a fixed argv array without a shell, with limits and redaction."""
    if not argv:
        raise ValueError("argv must not be empty")
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    try:
        proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return CmdResult(argv=tuple(argv), exit_code=None, stdout="", stderr="", error=str(exc))

    input_bytes = input_text.encode("utf-8") if input_text is not None else None
    try:
        out_bytes, err_bytes = proc.communicate(input=input_bytes, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        out_bytes, err_bytes = proc.communicate()
        stdout, out_truncated = _decode(out_bytes)
        stderr, err_truncated = _decode(err_bytes)
        return CmdResult(
            argv=tuple(argv),
            exit_code=None,
            stdout=redact_text(stdout),
            stderr=redact_text(stderr),
            timed_out=True,
            truncated=out_truncated or err_truncated,
        )
    stdout, out_truncated = _decode(out_bytes)
    stderr, err_truncated = _decode(err_bytes)
    return CmdResult(
        argv=tuple(argv),
        exit_code=proc.returncode,
        stdout=redact_text(stdout),
        stderr=redact_text(stderr),
        truncated=out_truncated or err_truncated,
    )


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _decode(data: bytes | None) -> tuple[str, bool]:
    if not data:
        return "", False
    truncated = len(data) > MAX_STREAM_BYTES
    text = data[:MAX_STREAM_BYTES].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n...[truncated {len(data) - MAX_STREAM_BYTES} bytes]"
    return text, truncated
