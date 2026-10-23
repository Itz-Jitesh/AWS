from __future__ import annotations

from pathlib import Path

import pytest

from app.checks import ALLOWED_SUBCOMMANDS, CHECKS, expand_checks
from app.sandbox import SandboxPolicyError, run_tool

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_no_shell_invocation_in_app_code():
    offenders = []
    for path in sorted(APP_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in ("shell=True", "os.system(", "os.popen(", "commands.getoutput"):
            if needle in source:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == []


def test_check_registry_only_uses_allowlisted_subcommands():
    for name, spec in CHECKS.items():
        assert spec.argv[0] in ALLOWED_SUBCOMMANDS, name
        assert "apply" not in spec.argv, name


def test_no_check_can_request_terraform_apply():
    for requested in ({"fmt"}, {"validate"}, {"plan"}, {"show_json"}):
        order = expand_checks(requested)
        for name in order:
            assert "apply" not in CHECKS[name].argv


def test_runner_rejects_non_allowlisted_binary(env):
    settings = env.make_settings()
    with pytest.raises(SandboxPolicyError):
        run_tool(
            settings,
            ["/bin/echo", "hi"],
            cwd=env.tmp_path,
            workspace=settings.data_dir,
            timeout_s=5,
            stdout_path=settings.data_dir / "x.out",
            stderr_path=settings.data_dir / "x.err",
            allowed_binaries={"terraform"},
        )


def test_runner_rejects_nul_byte_in_args(env):
    settings = env.make_settings()
    with pytest.raises(SandboxPolicyError):
        run_tool(
            settings,
            ["terraform", "val\x00idate"],
            cwd=env.tmp_path,
            workspace=settings.data_dir,
            timeout_s=5,
            stdout_path=settings.data_dir / "x.out",
            stderr_path=settings.data_dir / "x.err",
            allowed_binaries={"terraform"},
        )


def test_apply_is_not_a_valid_check_type():
    from pydantic import ValidationError

    from app.models import CheckRequest

    with pytest.raises(ValidationError):
        CheckRequest(task_id="a" * 32, checks=["apply"])


def test_task_id_path_traversal_rejected(env):
    client = env.client()
    for bad in ["../" * 10 + "etc", "..%2Fetc", "a" * 31 + "/", "A" * 32, ""]:
        response = client.post("/check", json={"task_id": bad, "checks": ["fmt"]})
        assert response.status_code == 422, bad


def test_workspace_task_id_cannot_escape_data_dir(env):
    from app.store import TaskStore

    store = TaskStore(env.make_settings())
    for bad in ["../outside", "/etc", "a/b/c", "..", ""]:
        with pytest.raises(KeyError):
            store.get(bad)
