"""Normalization of raw scanner records into contract-valid Finding payloads.

Rules enforced here:

* every finding carries a valid ``rule_source``, rule identifier, ``status``,
  and non-empty ``evidence``;
* evidence is either supplied by the scanner or derived only from concrete
  fields the scanner actually emitted — it is never invented;
* failure states (``UnableToVerify``, ``NotConfigured``, ``Skipped``) pass
  through unchanged;
* ``finding_id`` and ``fingerprint`` are deterministic so regression
  comparison can match findings across runs.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from .contracts import validate_all
from .errors import NormalizationError
from .redact import redact_text

SCHEMA_VERSION = "1.0.0"
RULE_SOURCES = ("checkov", "opa", "terraform", "custom")
STATUSES = ("Passed", "Failed", "Skipped", "NotConfigured", "UnableToVerify")
SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")

_SEVERITY_ALIASES = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "low": "low",
    "info": "info",
    "informational": "info",
    "unknown": "unknown",
}


def _first(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _coerce_severity(raw: Mapping[str, Any], context: str) -> str:
    value = _first(raw, "severity", "level")
    if value is None:
        return "unknown"
    if not isinstance(value, str):
        raise NormalizationError(f"{context}: severity {value!r} is not a string")
    severity = _SEVERITY_ALIASES.get(value.strip().lower())
    if severity is None:
        raise NormalizationError(f"{context}: severity {value!r} is not recognised")
    return severity


def _coerce_line_start(raw: Mapping[str, Any], context: str) -> int | None:
    value = _first(raw, "line_start")
    if value is None:
        line_range = raw.get("file_line_range")
        if isinstance(line_range, (list, tuple)) and line_range:
            value = line_range[0]
    if value is None:
        return None
    if isinstance(value, bool):
        raise NormalizationError(f"{context}: line_start {value!r} is not a line number")
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or value < 1:
        raise NormalizationError(f"{context}: line_start {value!r} is not a line number >= 1")
    return value


def _extract_evidence(
    raw: Mapping[str, Any],
    context: str,
    *,
    description: Any,
    resource_address: Any,
    file_path: Any,
    line_start: int | None,
) -> str:
    supplied = _first(raw, "evidence")
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()
    parts: list[str] = []
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    if isinstance(resource_address, str) and resource_address.strip():
        parts.append(f"resource {resource_address.strip()}")
    if isinstance(file_path, str) and file_path.strip():
        location = f"file {file_path.strip()}"
        if line_start is not None:
            location += f":{line_start}"
        parts.append(location)
    tool = _first(raw, "tool", "scanner")
    if isinstance(tool, str):
        parts.append(f"scanner {tool}")
    evidence = "; ".join(parts)
    if not evidence:
        raise NormalizationError(
            f"{context}: no evidence available; refusing to fabricate evidence"
        )
    return evidence


def normalize(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Turn raw scanner records into contract-valid Finding payloads."""
    if findings is None or isinstance(findings, (str, bytes, Mapping)):
        raise NormalizationError("normalize() expects an iterable of raw findings, not a scalar")
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(findings):
        if not isinstance(raw, Mapping):
            raise NormalizationError(f"finding {index} is not an object")
        output.append(_normalize_one(raw, index))
    validate_all(output, "finding")
    return output


def _normalize_one(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    source = _first(raw, "rule_source", "source")
    if source is None:
        raise NormalizationError(f"finding {index}: missing rule_source")
    if source not in RULE_SOURCES:
        raise NormalizationError(
            f"finding {index}: rule_source {source!r} is not one of {RULE_SOURCES}"
        )

    rule_id = _first(raw, "rule_id", "check_id", "bc_check_id", "policy_id", "id")
    if rule_id is None:
        raise NormalizationError(f"finding {index}: missing rule identifier")

    context = f"finding {index} ({source}/{rule_id})"
    status = raw.get("status")
    if status is None:
        raise NormalizationError(f"{context}: missing status")
    if status not in STATUSES:
        raise NormalizationError(f"{context}: status {status!r} is not one of {STATUSES}")

    severity = _coerce_severity(raw, context)

    title = _first(raw, "title", "short_description", "check_name", "name")
    if title is None:
        title = str(rule_id)
    title = str(title).strip() or str(rule_id)

    description = _first(raw, "description", "long_description", "msg", "message")
    if description is not None:
        description = str(description).strip() or None

    resource_address = _first(raw, "resource_address", "resource")
    if resource_address is not None:
        resource_address = str(resource_address).strip() or None

    file_path = _first(raw, "file_path", "file")
    if file_path is not None:
        file_path = str(file_path).strip() or None

    line_start = _coerce_line_start(raw, context)

    evidence = _extract_evidence(
        raw,
        context,
        description=description,
        resource_address=resource_address,
        file_path=file_path,
        line_start=line_start,
    )

    identity = "\x1e".join(
        str(part)
        for part in (source, str(rule_id), resource_address or "", file_path or "", line_start or "", title)
    )
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    finding: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "finding_id": f"fnd_{fingerprint[:24]}",
        "rule_source": str(source),
        "rule_id": str(rule_id),
        "severity": severity,
        "status": status,
        "title": redact_text(title),
        "evidence": redact_text(evidence),
        "fingerprint": fingerprint,
    }
    if description is not None:
        finding["description"] = redact_text(description)
    if resource_address is not None:
        finding["resource_address"] = resource_address
    if file_path is not None:
        finding["file_path"] = file_path
    if line_start is not None:
        finding["line_start"] = line_start
    remediation = _first(raw, "remediation")
    if isinstance(remediation, str) and remediation.strip():
        finding["remediation"] = redact_text(remediation.strip())
    return finding
