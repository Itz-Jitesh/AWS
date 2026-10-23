from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings

try:
    import resource as _resource
except ImportError:
    _resource = None

ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
    }
)


class SandboxPolicyError(Exception):
    pass


@dataclass
class ToolResult:
    argv: list[str]
    started_at: str
    duration_ms: int
    exit_code: int | None = None
    timed_out: bool = False
    killed_by_signal: bool = False
    signal_name: str | None = None
    spawn_error: str | None = None
    stdout_text: str = ""
    stderr_text: str = ""
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_env(settings: Settings, workspace: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in sorted(ENV_ALLOWLIST) if key in os.environ}
    env["HOME"] = str(workspace / "home")
    env["TMPDIR"] = str(workspace / "tmp")
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_INPUT"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_ALLOW_PROTOCOL"] = "https"
    if not env.get("PATH"):
        env["PATH"] = "/usr/bin:/bin"
    return env


def _set_limit(name: str, soft: int, hard: int | None = None) -> None:
    try:
        import resource
    except ImportError:
        return
    limit = getattr(resource, name, None)
    if limit is None:
        return
    try:
        resource.setrlimit(limit, (soft, soft if hard is None else hard))
    except (ValueError, OSError):
        return


def _apply_resource_limits(cpu_seconds: int, max_output_file_bytes: int) -> None:
    _set_limit("RLIMIT_CORE", 0)
    _set_limit("RLIMIT_CPU", cpu_seconds)
    _set_limit("RLIMIT_FSIZE", max_output_file_bytes)
    _set_limit("RLIMIT_NOFILE", 256)
    _set_limit("RLIMIT_NPROC", 512)


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _read_capped(path: Path, cap: int) -> tuple[str, bool]:
    try:
        with path.open("rb") as handle:
            data = handle.read(cap + 1)
    except OSError:
        return "", False
    truncated = len(data) > cap
    if truncated:
        data = data[:cap]
    return data.decode("utf-8", errors="replace"), truncated


def run_tool(
    settings: Settings,
    argv: list[str],
    *,
    cwd: Path,
    workspace: Path,
    timeout_s: int,
    stdout_path: Path,
    stderr_path: Path,
    allowed_binaries: set[str],
) -> ToolResult:
    if not argv or not isinstance(argv[0], str):
        raise SandboxPolicyError("argv must be a non-empty list of strings")
    if argv[0] not in allowed_binaries:
        raise SandboxPolicyError(f"binary not allowlisted: {argv[0]!r}")
    for arg in argv:
        if not isinstance(arg, str):
            raise SandboxPolicyError("argv entries must be strings")
        if "\x00" in arg:
            raise SandboxPolicyError("NUL byte in argv")

    started_at = utc_now_iso()
    started = time.monotonic()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    result = ToolResult(argv=list(argv), started_at=started_at, duration_ms=0)

    cpu_limit = max(timeout_s + 5, 5)
    try:
        with stdout_path.open("wb") as out_handle, stderr_path.open("wb") as err_handle:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=str(cwd),
                    env=build_env(settings, workspace),
                    stdin=subprocess.DEVNULL,
                    stdout=out_handle,
                    stderr=err_handle,
                    close_fds=True,
                    start_new_session=True,
                    preexec_fn=lambda: _apply_resource_limits(cpu_limit, settings.max_output_file_bytes),
                )
            except FileNotFoundError:
                result.spawn_error = "not_found"
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
            except PermissionError:
                result.spawn_error = "permission_denied"
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
            except OSError as exc:
                result.spawn_error = f"spawn_failed:{exc.__class__.__name__}"
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result

            timed_out = False
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_group(proc)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        result.duration_ms = int((time.monotonic() - started) * 1000)

    returncode = proc.returncode
    if timed_out:
        result.timed_out = True
        result.limitations.append(f"timed out after {timeout_s}s and was killed")
    elif returncode is not None and returncode < 0:
        result.killed_by_signal = True
        try:
            result.signal_name = signal.Signals(-returncode).name
        except ValueError:
            result.signal_name = str(-returncode)
        result.limitations.append(f"terminated by signal {result.signal_name}")
    elif returncode is not None:
        result.exit_code = returncode
    else:
        result.spawn_error = result.spawn_error or "no_exit_code"
        result.limitations.append("process produced no exit code")

    stdout_text, stdout_truncated = _read_capped(stdout_path, settings.max_output_read_bytes)
    stderr_text, stderr_truncated = _read_capped(stderr_path, settings.max_output_read_bytes)
    result.stdout_text = stdout_text
    result.stderr_text = stderr_text
    if stdout_truncated or stderr_truncated:
        result.truncated = True
        result.limitations.append(
            f"output truncated to first {settings.max_output_read_bytes} bytes"
        )
    return result
