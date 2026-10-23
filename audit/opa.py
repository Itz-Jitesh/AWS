"""OPA adapter.

``run_opa(workspace, plan_json) -> Finding[]`` evaluates the bundled Rego
policy set against the Terraform plan through ``opa eval`` with a fixed
argument array. ``workspace`` is validated for interface compatibility and
future workspace-scoped policies; today the policies evaluate the plan
document only (``input.plan``).

Failure handling mirrors the Checkov adapter: missing binary, invalid plan
input, policy-set problems, timeout, non-zero exit, and malformed output all
produce explicit operational Findings — never a pass.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .errors import NormalizationError
from .normalize import normalize
from .operational import operational_finding
from .runner import DEFAULT_TIMEOUT_SEC, resolve_scanner, run_argv

TOOL = "opa"
_ENV_VAR = "PLANPROOF_OPA_BIN"
DEFAULT_POLICIES_DIR = Path(__file__).resolve().parent / "policies"
QUERY = "data.planproof.deny.deny"


def run_opa(
    workspace: str | Path,
    plan_json: Any,
    *,
    executable: str | None = None,
    policies_dir: str | Path | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Evaluate Rego policies against ``plan_json`` and return Findings."""
    ws = Path(workspace) if workspace is not None else None
    if ws is None or not ws.is_dir():
        return [
            operational_finding(
                TOOL, "workspace_missing", f"workspace not found: {workspace}"
            )
        ]
    if not isinstance(plan_json, dict):
        return [
            operational_finding(
                TOOL,
                "invalid_plan",
                "plan input for policy evaluation is not a JSON object: "
                f"{type(plan_json).__name__}",
            )
        ]

    policies = Path(policies_dir) if policies_dir is not None else DEFAULT_POLICIES_DIR
    if not policies.is_dir():
        return [
            operational_finding(
                TOOL, "policy_unavailable", f"policy directory not found: {policies}"
            )
        ]
    if not any(policies.glob("*.rego")):
        return [
            operational_finding(
                TOOL, "policy_unavailable", f"no .rego policies found in {policies}"
            )
        ]

    path, origin = resolve_scanner(executable, TOOL, _ENV_VAR)
    if path is None:
        return [operational_finding(TOOL, "binary_missing", origin)]

    try:
        input_document = json.dumps({"plan": plan_json}, default=str)
    except (TypeError, ValueError) as exc:
        return [
            operational_finding(
                TOOL, "invalid_plan", f"plan input is not serializable to JSON: {exc}"
            )
        ]

    with tempfile.TemporaryDirectory(prefix="planproof-opa-") as tmp:
        input_path = Path(tmp) / "input.json"
        input_path.write_text(input_document, encoding="utf-8")
        result = run_argv(
            [
                path,
                "eval",
                "--format",
                "json",
                "-d",
                str(policies),
                "-i",
                str(input_path),
                QUERY,
            ],
            cwd=tmp,
            timeout_sec=timeout_sec,
        )
        if result.timed_out:
            return [
                operational_finding(
                    TOOL,
                    "timeout",
                    f"{TOOL} exceeded time limit of {timeout_sec}s{_stderr_hint(result)}",
                )
            ]
        if result.error is not None:
            return [
                operational_finding(
                    TOOL, "execution_failed", f"{TOOL} could not be executed: {result.error}"
                )
            ]
        if result.exit_code != 0:
            detail = f"{TOOL} eval failed with exit code {result.exit_code}"
            tail = (result.stderr or result.stdout or "").strip()[-400:]
            if tail:
                detail += f"; {tail}"
            return [operational_finding(TOOL, "eval_failed", detail)]

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return [
                operational_finding(
                    TOOL,
                    "malformed_output",
                    f"{TOOL} output is not parseable JSON: {exc}{_stderr_hint(result)}",
                )
            ]

    denials, parse_error = _extract_denials(payload)
    if parse_error:
        return [operational_finding(TOOL, "malformed_output", parse_error)]
    if not denials:
        return []

    raw_findings: list[dict[str, Any]] = []
    try:
        for denial in denials:
            raw_findings.append(_map_denial(denial))
        return normalize(raw_findings)
    except NormalizationError as exc:
        return [
            operational_finding(
                TOOL, "malformed_output", f"{TOOL} denial results could not be normalized: {exc}"
            )
        ]


def _stderr_hint(result: Any) -> str:
    tail = str(result.stderr or "").strip()[-400:]
    return f"; stderr: {tail}" if tail else ""


def _extract_denials(payload: Any) -> tuple[list[Any], str]:
    if not isinstance(payload, dict):
        return [], f"opa eval payload is {type(payload).__name__}, expected object"
    result = payload.get("result")
    if not isinstance(result, list):
        return [], "opa eval payload has no result array"
    if not result:
        return [], (
            "opa eval returned no result for query "
            f"{QUERY}; policy package missing or query undefined"
        )
    first = result[0]
    if not isinstance(first, dict) or not isinstance(first.get("expressions"), list):
        return [], "opa eval payload result[0] has no expressions array"
    expressions = first["expressions"]
    if not expressions:
        return [], "opa eval result[0] contains no expressions"
    expression = expressions[0]
    if not isinstance(expression, dict):
        return [], "opa eval expression is not an object"
    value = expression.get("value")
    if not isinstance(value, list):
        return [], "opa eval expression value is not an array/set"
    for item in value:
        if not isinstance(item, dict):
            return [], "opa denial entry is not an object"
    return value, ""


def _map_denial(denial: dict[str, Any]) -> dict[str, Any]:
    rule_id = denial.get("rule")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise NormalizationError("opa denial has no rule id")
    message = denial.get("msg")
    if not isinstance(message, str) or not message.strip():
        raise NormalizationError(f"opa denial {rule_id} has no message")
    raw: dict[str, Any] = {
        "rule_source": "opa",
        "rule_id": rule_id.strip(),
        "status": "Failed",
        "evidence": message.strip(),
    }
    title = denial.get("title")
    if isinstance(title, str) and title.strip():
        raw["title"] = title.strip()
    severity = denial.get("severity")
    if isinstance(severity, str) and severity.strip():
        raw["severity"] = severity.strip()
    resource = denial.get("resource")
    if isinstance(resource, str) and resource.strip():
        raw["resource_address"] = resource.strip()
    return raw
