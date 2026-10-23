"""Checkov adapter.

``run_checkov(workspace) -> Finding[]`` runs Checkov against a workspace with
a fixed argument array (never an LLM-built command) and normalizes its JSON
output. Every failure mode — missing binary, timeout, crash, malformed or
empty output — becomes an explicit ``UnableToVerify``/``NotConfigured``
operational Finding; none of them can surface as ``Passed``.
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

TOOL = "checkov"
_ENV_VAR = "PLANPROOF_CHECKOV_BIN"
_RESULT_LISTS = (
    ("failed_checks", "Failed"),
    ("passed_checks", "Passed"),
    ("skipped_checks", "Skipped"),
)
_SEVERITY_ALIASES = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
}


def run_checkov(
    workspace: str | Path,
    *,
    executable: str | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Scan ``workspace`` with Checkov and return normalized Findings."""
    ws = Path(workspace) if workspace is not None else None
    if ws is None or not ws.is_dir():
        return [
            operational_finding(
                TOOL, "workspace_missing", f"workspace not found: {workspace}"
            )
        ]

    path, origin = resolve_scanner(executable, TOOL, _ENV_VAR)
    if path is None:
        return [operational_finding(TOOL, "binary_missing", origin)]

    with tempfile.TemporaryDirectory(prefix="planproof-checkov-") as tmp:
        result = run_argv(
            [path, "-d", str(ws), "-o", "json"],
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

        data, origin_label, parse_error = _parse_payload(result.stdout, "stdout")
        if data is None:
            fallback = Path(tmp) / "results_json.json"
            if fallback.is_file():
                data, origin_label, parse_error = _parse_payload(
                    fallback.read_text(encoding="utf-8", errors="replace"),
                    "results_json.json",
                )
        if data is None:
            detail = f"{TOOL} output from {origin_label} is not parseable JSON: {parse_error}"
            if result.exit_code is not None:
                detail += f"; exit code {result.exit_code}"
            return [
                operational_finding(
                    TOOL, "malformed_output", detail + _stderr_hint(result)
                )
            ]

    return _findings_from_payload(data)


def _parse_payload(payload: str, origin: str) -> tuple[dict[str, Any] | None, str, str]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, origin, str(exc)
    if not isinstance(parsed, dict):
        return None, origin, f"top level is {type(parsed).__name__}, expected object"
    return parsed, origin, ""


def _stderr_hint(result: Any) -> str:
    tail = str(result.stderr or "").strip()[-400:]
    return f"; stderr: {tail}" if tail else ""


def _summary_of(payload: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = results.get("summary")
    return summary if isinstance(summary, dict) else {}


def _findings_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, dict):
        return [
            operational_finding(
                TOOL, "malformed_output", "checkov JSON has no results object"
            )
        ]

    raw_findings: list[dict[str, Any]] = []
    try:
        for list_name, status in _RESULT_LISTS:
            entries = results.get(list_name) or []
            if not isinstance(entries, list):
                raise NormalizationError(f"results.{list_name} is not an array")
            for entry in entries:
                raw_findings.append(_map_entry(entry, status))
    except NormalizationError as exc:
        return [
            operational_finding(
                TOOL, "malformed_output", f"checkov results could not be normalized: {exc}"
            )
        ]

    coverage_gap = _parsing_error_finding(results)

    if not raw_findings:
        if coverage_gap is not None:
            return [coverage_gap]
        summary = _summary_of(payload, results)
        detail = "checkov returned no check results"
        if summary:
            detail += f"; summary: {json.dumps(summary, sort_keys=True, default=str)}"
        return [operational_finding(TOOL, "no_results", detail, status="NotConfigured")]

    try:
        findings = normalize(raw_findings)
    except NormalizationError as exc:
        return [
            operational_finding(
                TOOL, "malformed_output", f"checkov results could not be normalized: {exc}"
            )
        ]
    if coverage_gap is not None:
        findings.append(coverage_gap)
    return findings


def _parsing_error_finding(results: dict[str, Any]) -> dict[str, Any] | None:
    errors = results.get("parsing_errors")
    if not isinstance(errors, list) or not errors:
        return None
    detail = json.dumps(errors[:5], default=str)
    if len(detail) > 500:
        detail = detail[:500] + "..."
    return operational_finding(
        TOOL,
        "partial_scan",
        f"checkov could not parse {len(errors)} file(s); per-check results are "
        f"incomplete and must not be read as a full pass: {detail}",
    )


def _map_entry(entry: Any, status: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise NormalizationError("checkov result entry is not an object")
    rule_id = entry.get("check_id") or entry.get("bc_check_id") or entry.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise NormalizationError("checkov result entry has no check_id")

    raw: dict[str, Any] = {
        "rule_source": "checkov",
        "rule_id": rule_id.strip(),
        "status": status,
        "title": entry.get("short_description")
        or entry.get("check_name")
        or entry.get("name")
        or rule_id,
    }
    severity = _entry_severity(entry)
    if severity is not None:
        raw["severity"] = severity
    description = (
        entry.get("short_description")
        or entry.get("check_name")
        or entry.get("long_description")
    )
    if isinstance(description, str) and description.strip():
        raw["description"] = description.strip()
    resource = entry.get("resource")
    if isinstance(resource, str) and resource.strip():
        raw["resource_address"] = resource.strip()
    file_path = entry.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        raw["file_path"] = file_path.strip()
    line_range = entry.get("file_line_range")
    if isinstance(line_range, (list, tuple)) and line_range:
        raw["file_line_range"] = list(line_range)
    guideline = entry.get("guideline")
    if isinstance(guideline, str) and guideline.strip():
        raw["remediation"] = guideline.strip()
    return raw


def _entry_severity(entry: dict[str, Any]) -> str | None:
    for key in ("severity", "level"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            mapped = _SEVERITY_ALIASES.get(value.strip().lower())
            if mapped is not None:
                return mapped
    return None
