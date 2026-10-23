from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .artifacts import store_plan, write_text_artifact
from .config import Settings
from .contracts import ensure_contract
from .models import CheckRun, CheckStatus, CheckType
from .redact import redact_text
from .sandbox import ToolResult, run_tool, utc_now_iso
from .store import TaskPaths

ALLOWED_SUBCOMMANDS = frozenset({"fmt", "init", "validate", "plan", "show", "version"})


@dataclass(frozen=True)
class CheckSpec:
    name: str
    argv: tuple[str, ...]
    requires: tuple[str, ...]


CHECKS: dict[str, CheckSpec] = {
    "fmt": CheckSpec("fmt", ("fmt", "-check", "-recursive"), ()),
    "init": CheckSpec("init", ("init", "-backend=false", "-input=false", "-no-color"), ()),
    "validate": CheckSpec("validate", ("validate", "-no-color"), ("init",)),
    "plan": CheckSpec("plan", ("plan", "-input=false", "-no-color", "-out=tfplan"), ("init",)),
    "show_json": CheckSpec("show_json", ("show", "-json", "tfplan"), ("plan",)),
}

CHECK_ORDER: tuple[str, ...] = ("fmt", "init", "validate", "plan", "show_json")


def expand_checks(requested: set[str]) -> list[str]:
    needed = set(requested)
    changed = True
    while changed:
        changed = False
        for name in sorted(needed):
            for dependency in CHECKS[name].requires:
                if dependency not in needed:
                    needed.add(dependency)
                    changed = True
    return [name for name in CHECK_ORDER if name in needed]


def probe_terraform_version(settings: Settings, cache: dict[str, str | None]) -> str | None:
    key = settings.terraform_bin
    if key in cache:
        return cache[key]
    if shutil.which(settings.terraform_bin) is None:
        cache[key] = None
        return None
    tmp_dir = settings.data_dir / "tmp"
    home_dir = settings.data_dir / "home"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    result = run_tool(
        settings,
        [settings.terraform_bin, "version"],
        cwd=settings.data_dir,
        workspace=settings.data_dir,
        timeout_s=settings.version_probe_timeout_s,
        stdout_path=tmp_dir / "version.stdout.log",
        stderr_path=tmp_dir / "version.stderr.log",
        allowed_binaries={settings.terraform_bin},
    )
    version: str | None = None
    if result.exit_code == 0 and result.stdout_text.strip():
        version = result.stdout_text.strip().splitlines()[0].strip()
    cache[key] = version
    return version


def _command_label(argv: list[str]) -> str:
    return " ".join([Path(argv[0]).name, *argv[1:]])


def _failure_summary(label: str, stderr_text: str, exit_code: int | None) -> str:
    for line in stderr_text.splitlines():
        stripped = line.strip()
        if stripped:
            return redact_text(stripped)[:300]
    return f"{label} exited with code {exit_code}"


def _interpret(
    result: ToolResult,
    spec: CheckSpec,
    settings: Settings,
    check_id: str,
    tool_version: str | None,
    stdout_rel: str,
    stderr_rel: str,
) -> CheckRun:
    label = _command_label(result.argv)
    limitations = list(result.limitations)
    exit_code = result.exit_code
    if result.spawn_error == "not_found":
        status: CheckStatus = "UnableToVerify"
        summary = f"required executable not found: {settings.terraform_bin}"
        limitations.append(
            f"executable '{settings.terraform_bin}' is not available on PATH; check not executed"
        )
        exit_code = None
    elif result.spawn_error:
        status = "UnableToVerify"
        summary = f"could not start {label}: {result.spawn_error}"
        limitations.append(f"process failed to start: {result.spawn_error}")
        exit_code = None
    elif result.timed_out:
        status = "UnableToVerify"
        summary = f"{label} timed out after {settings.check_timeout_s}s"
        exit_code = None
    elif result.killed_by_signal:
        status = "UnableToVerify"
        summary = f"{label} terminated by signal {result.signal_name}"
        exit_code = None
    elif exit_code == 0:
        status = "Passed"
        summary = f"{label} succeeded"
    else:
        status = "Failed"
        summary = _failure_summary(label, result.stderr_text, exit_code)
    return ensure_contract(
        CheckRun(
            check_id=check_id,
            tool="terraform",
            status=status,
            started_at=result.started_at,
            duration_ms=result.duration_ms,
            summary=summary,
            exit_code=exit_code,
            tool_version=tool_version,
            stdout_artifact=stdout_rel,
            stderr_artifact=stderr_rel,
            limitations=limitations,
        )
    )


def _unverifiable(
    check_id: str,
    started_at: str,
    summary: str,
    limitation: str,
    stdout_rel: str,
    stderr_rel: str,
) -> CheckRun:
    return ensure_contract(
        CheckRun(
            check_id=check_id,
            tool="terraform",
            status="UnableToVerify",
            started_at=started_at,
            duration_ms=0,
            summary=summary,
            exit_code=None,
            tool_version=None,
            stdout_artifact=stdout_rel,
            stderr_artifact=stderr_rel,
            limitations=[limitation],
        )
    )


def run_checks(
    settings: Settings,
    paths: TaskPaths,
    requested: list[CheckType],
    version_cache: dict[str, str | None],
) -> list[CheckRun]:
    order = expand_checks(set(requested))
    runs: list[CheckRun] = []
    outcomes: dict[str, str] = {}
    tool_version = probe_terraform_version(settings, version_cache)
    for name in order:
        spec = CHECKS[name]
        check_id = f"{paths.task_id}:{name}"
        started_at = utc_now_iso()
        prerequisite = next(
            (dep for dep in spec.requires if outcomes.get(dep) != "Passed"), None
        )
        if prerequisite is not None:
            stdout_rel = write_text_artifact(paths, f"{name}.stdout.log", "")
            stderr_rel = write_text_artifact(paths, f"{name}.stderr.log", "")
            run = _unverifiable(
                check_id,
                started_at,
                summary=f"{name} not executed: prerequisite '{prerequisite}' did not pass",
                limitation=(
                    f"prerequisite check '{prerequisite}' ended with status "
                    f"{outcomes.get(prerequisite)}; result cannot be verified"
                ),
                stdout_rel=stdout_rel,
                stderr_rel=stderr_rel,
            )
            runs.append(run)
            outcomes[name] = run.status
            continue
        if name == "show_json" and not (paths.repo / "tfplan").is_file():
            stdout_rel = write_text_artifact(paths, f"{name}.stdout.log", "")
            stderr_rel = write_text_artifact(paths, f"{name}.stderr.log", "")
            run = _unverifiable(
                check_id,
                started_at,
                summary="show_json not executed: plan artifact missing",
                limitation="plan file 'tfplan' not present in the workspace; run the 'plan' check first",
                stdout_rel=stdout_rel,
                stderr_rel=stderr_rel,
            )
            runs.append(run)
            outcomes[name] = run.status
            continue

        argv = [settings.terraform_bin, *spec.argv]
        result = run_tool(
            settings,
            argv,
            cwd=paths.repo,
            workspace=paths.root,
            timeout_s=settings.check_timeout_s,
            stdout_path=paths.artifacts / f"{name}.stdout.raw",
            stderr_path=paths.artifacts / f"{name}.stderr.raw",
            allowed_binaries={settings.terraform_bin},
        )
        if name == "show_json" and result.exit_code == 0:
            raw_path = paths.artifacts / f"{name}.stdout.raw"
            if raw_path.is_file() and raw_path.stat().st_size > 0:
                store_plan(paths, raw_path.read_text(encoding="utf-8", errors="replace"))
        stdout_rel = write_text_artifact(paths, f"{name}.stdout.log", result.stdout_text)
        stderr_rel = write_text_artifact(paths, f"{name}.stderr.log", result.stderr_text)
        for suffix in ("stdout", "stderr"):
            raw = paths.artifacts / f"{name}.{suffix}.raw"
            if raw.exists():
                raw.unlink()
        run = _interpret(
            result,
            spec,
            settings,
            check_id,
            tool_version,
            stdout_rel,
            stderr_rel,
        )
        runs.append(run)
        outcomes[name] = run.status
    return runs
