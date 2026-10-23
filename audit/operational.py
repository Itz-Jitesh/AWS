"""Operational failure records for scanner runs.

A missing binary, timeout, crash, or malformed scanner output is an
operational failure, not a policy finding. Because the shared Finding schema
(1.0.0) has no dedicated field to say "this record is not a policy result",
operational failures are represented as Findings with:

* ``rule_source`` = ``"custom"`` (never ``"checkov"``/``"opa"``, so they can
  never be mistaken for a scanner's own rule results);
* ``rule_id`` in the reserved ``scanner.<tool>.<kind>`` namespace;
* ``severity`` = ``"unknown"`` (no severity claim is made);
* ``status`` = ``"UnableToVerify"`` (or ``"NotConfigured"``);
* ``evidence`` describing exactly what went wrong, redacted.

This is a documented limitation of schema 1.0.0. Proposed extension for a
future coordinated version bump: a ``record_kind: "policy" | "operational"``
field (or a sibling ``ScannerFailure`` contract) so consumers can separate
the two without relying on the rule_id namespace convention.
"""

from __future__ import annotations

import re

from .errors import NormalizationError
from .normalize import normalize
from .redact import redact_text

_KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_STATUSES = ("UnableToVerify", "NotConfigured")


def operational_raw(
    tool: str,
    kind: str,
    evidence: str,
    *,
    status: str = "UnableToVerify",
    description: str | None = None,
) -> dict[str, str]:
    """Build the raw record for an operational failure (pre-normalization)."""
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("tool must be a non-empty string")
    if not isinstance(kind, str) or not _KIND_RE.fullmatch(kind):
        raise ValueError(f"kind {kind!r} must match [a-z][a-z0-9_]*")
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"operational status must be one of {_ALLOWED_STATUSES}")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("operational failure requires real, non-empty evidence")
    raw: dict[str, str] = {
        "rule_source": "custom",
        "rule_id": f"scanner.{tool.strip()}.{kind}",
        "severity": "unknown",
        "status": status,
        "title": f"{tool.strip()} scan not verified: {kind.replace('_', ' ')}",
        "evidence": redact_text(evidence.strip()),
    }
    if description:
        raw["description"] = redact_text(description.strip())
    return raw


def operational_finding(
    tool: str,
    kind: str,
    evidence: str,
    *,
    status: str = "UnableToVerify",
    description: str | None = None,
) -> dict[str, object]:
    """Return one contract-valid operational Finding."""
    try:
        raw = operational_raw(tool, kind, evidence, status=status, description=description)
    except ValueError as exc:
        raise NormalizationError(str(exc)) from exc
    return normalize([raw])[0]
