"""Regression comparison between two normalized Finding sets.

Semantics (documented for Agents A and C):

* ``regressions`` — findings that became ``Failed`` (new or previously
  non-failing) with severity ``critical``/``high``;
* ``new_findings`` — every record present only in ``after``;
* ``resolved`` — a ``Failed`` finding that ``after`` proves passed (explicit
  ``Passed`` counterpart, or absence while the after scan is complete);
* ``unconfirmed_resolved`` — would-be resolutions that lack confirming
  evidence because the after set carries ``UnableToVerify``/``NotConfigured``
  records or is empty. These are NEVER resolutions;
* ``missing_after`` — previously non-failing records that disappeared without
  evidence; disappearance is not a pass;
* ``unchanged`` — same fingerprint and non-gap status on both sides
  (persistent gaps are reported once under ``evidence_gaps``);
* ``status_changes`` — same fingerprint, different status (excluding entries
  already classified as regression/resolution/gap);
* ``evidence_gaps`` — ``UnableToVerify``/``NotConfigured`` records from either
  side; scanner failures are never security results;
* ``has_regressions`` — ``regressions`` is non-empty;
* ``resolved_confirmed`` — no unconfirmed resolutions exist;
* ``after_scan_complete`` — after set is non-empty and gap-free.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .contracts import validate_all
from .errors import ContractValidationError

GAP_STATUSES = frozenset({"UnableToVerify", "NotConfigured"})
REGRESSION_SEVERITIES = frozenset({"critical", "high"})
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


@dataclass
class RegressionResult:
    """Outcome of :func:`compare` (JSON-serializable via :meth:`to_dict`)."""

    regressions: list[dict[str, Any]] = field(default_factory=list)
    new_findings: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    unconfirmed_resolved: list[dict[str, Any]] = field(default_factory=list)
    missing_after: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[dict[str, Any]] = field(default_factory=list)
    status_changes: list[dict[str, Any]] = field(default_factory=list)
    evidence_gaps: list[dict[str, Any]] = field(default_factory=list)
    has_regressions: bool = False
    resolved_confirmed: bool = True
    after_scan_complete: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for HTTP/JSON transport."""
        return asdict(self)


def _validated(findings: Iterable[Mapping[str, Any]], side: str) -> list[dict[str, Any]]:
    if findings is None or isinstance(findings, (str, bytes, Mapping)):
        raise ContractValidationError(f"{side} findings must be a list of Finding objects")
    items = list(findings)
    validate_all(items, "finding")
    return items


def _index(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[finding["fingerprint"]].append(finding)
    return grouped


def _sort(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda f: (
            _SEVERITY_RANK.get(f["severity"], 99),
            f["rule_source"],
            f["rule_id"],
            f["fingerprint"],
        ),
    )


def _status_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": before["fingerprint"],
        "rule_source": before["rule_source"],
        "rule_id": before["rule_id"],
        "title": before["title"],
        "severity": after["severity"],
        "before_status": before["status"],
        "after_status": after["status"],
    }


def compare(
    before: Iterable[Mapping[str, Any]],
    after: Iterable[Mapping[str, Any]],
) -> RegressionResult:
    """Compare two normalized Finding sets and classify regressions."""
    before_items = _validated(before, "before")
    after_items = _validated(after, "after")

    result = RegressionResult()
    result.after_scan_complete = bool(after_items) and not any(
        f["status"] in GAP_STATUSES for f in after_items
    )
    if not after_items:
        result.notes.append(
            "after set is empty; no finding can be confirmed resolved without evidence"
        )
    elif not result.after_scan_complete:
        result.notes.append(
            "after set contains UnableToVerify/NotConfigured records; "
            "missing scanner evidence is not treated as a pass"
        )

    before_by = _index(before_items)
    after_by = _index(after_items)

    for fingerprint in sorted(set(before_by) | set(after_by)):
        before_group = before_by.get(fingerprint, [])
        after_group = after_by.get(fingerprint, [])

        for before_finding, after_finding in zip(before_group, after_group):
            before_status = before_finding["status"]
            after_status = after_finding["status"]
            if after_status in GAP_STATUSES:
                result.evidence_gaps.append(after_finding)
                if before_status in GAP_STATUSES:
                    continue
                if before_status == "Failed":
                    result.unconfirmed_resolved.append(before_finding)
                else:
                    result.status_changes.append(_status_change(before_finding, after_finding))
                continue
            if before_status == after_status:
                result.unchanged.append(after_finding)
                continue
            if after_status == "Failed" and before_status != "Failed":
                result.status_changes.append(_status_change(before_finding, after_finding))
                if after_finding["severity"] in REGRESSION_SEVERITIES:
                    result.regressions.append(after_finding)
                continue
            if before_status == "Failed" and after_status == "Passed":
                result.resolved.append(after_finding)
                continue
            result.status_changes.append(_status_change(before_finding, after_finding))

        for before_finding in before_group[len(after_group) :]:
            if before_finding["status"] in GAP_STATUSES:
                result.evidence_gaps.append(before_finding)
            elif before_finding["status"] == "Failed":
                if result.after_scan_complete:
                    result.resolved.append(before_finding)
                else:
                    result.unconfirmed_resolved.append(before_finding)
            else:
                result.missing_after.append(before_finding)

        for after_finding in after_group[len(before_group) :]:
            result.new_findings.append(after_finding)
            if after_finding["status"] in GAP_STATUSES:
                result.evidence_gaps.append(after_finding)
            elif (
                after_finding["status"] == "Failed"
                and after_finding["severity"] in REGRESSION_SEVERITIES
            ):
                result.regressions.append(after_finding)

    result.regressions = _sort(result.regressions)
    result.new_findings = _sort(result.new_findings)
    result.resolved = _sort(result.resolved)
    result.unconfirmed_resolved = _sort(result.unconfirmed_resolved)
    result.missing_after = _sort(result.missing_after)
    result.unchanged = _sort(result.unchanged)
    result.status_changes = sorted(
        result.status_changes, key=lambda c: (c["rule_source"], c["rule_id"], c["fingerprint"])
    )
    result.evidence_gaps = _sort(result.evidence_gaps)

    result.has_regressions = bool(result.regressions)
    result.resolved_confirmed = not result.unconfirmed_resolved
    if not result.resolved_confirmed:
        result.notes.append(
            f"{len(result.unconfirmed_resolved)} prior failure(s) lack confirming "
            "evidence and are reported as unconfirmed_resolved, not resolved"
        )
    return result
