"""Regression comparison tests, focused on evidence-gap honesty."""

from __future__ import annotations

import json

import pytest

from audit.contracts import validate
from audit.errors import ContractValidationError
from audit.normalize import normalize
from audit.operational import operational_finding
from audit.regression import compare

from .conftest import minimal_finding

FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


def _finding(fingerprint: str, **overrides) -> dict:
    return minimal_finding(fingerprint=fingerprint, **overrides)


def test_new_high_severity_finding_is_a_regression() -> None:
    before = [_finding(FP_A, status="Passed")]
    after = [
        _finding(FP_A, status="Passed"),
        _finding(FP_B, rule_id="CKV_AWS_20", severity="critical", status="Failed",
                 title="public bucket", evidence="bucket is public"),
    ]
    result = compare(before, after)
    assert result.has_regressions is True
    assert [f["fingerprint"] for f in result.regressions] == [FP_B]
    assert [f["fingerprint"] for f in result.new_findings] == [FP_B]
    assert result.resolved_confirmed is True


def test_new_medium_finding_is_not_a_regression_but_is_reported() -> None:
    after = [_finding(FP_B, severity="medium", status="Failed")]
    result = compare([], after)
    assert result.has_regressions is False
    assert result.regressions == []
    assert [f["fingerprint"] for f in result.new_findings] == [FP_B]


def test_finding_resolved_by_explicit_pass() -> None:
    before = [_finding(FP_A, status="Failed")]
    after = [_finding(FP_A, status="Passed")]
    result = compare(before, after)
    assert [f["fingerprint"] for f in result.resolved] == [FP_A]
    assert result.unconfirmed_resolved == []
    assert result.resolved_confirmed is True
    assert result.has_regressions is False


def test_unavailable_scanner_never_confirms_resolution() -> None:
    before = [
        _finding(FP_A, status="Failed", severity="critical"),
        _finding(FP_B, status="Failed", severity="high"),
    ]
    gap = operational_finding("checkov", "binary_missing", "checkov executable not found on PATH")
    after = [gap]
    result = compare(before, after)
    assert result.resolved == []
    assert sorted(f["fingerprint"] for f in result.unconfirmed_resolved) == [FP_A, FP_B]
    assert result.resolved_confirmed is False
    assert result.after_scan_complete is False
    assert result.has_regressions is False
    assert any(g["status"] == "UnableToVerify" for g in result.evidence_gaps)
    assert any("not treated as a pass" in note for note in result.notes)


def test_empty_after_set_cannot_confirm_resolutions() -> None:
    before = [_finding(FP_A, status="Failed")]
    result = compare(before, [])
    assert result.resolved == []
    assert [f["fingerprint"] for f in result.unconfirmed_resolved] == [FP_A]
    assert result.resolved_confirmed is False
    assert result.after_scan_complete is False


def test_complete_after_scan_confirms_absent_finding_resolved() -> None:
    before = [_finding(FP_A, status="Failed")]
    after = [_finding(FP_B, status="Passed", rule_id="OTHER")]
    result = compare(before, after)
    assert [f["fingerprint"] for f in result.resolved] == [FP_A]
    assert result.resolved_confirmed is True
    assert result.after_scan_complete is True


def test_after_gap_record_is_new_but_not_a_security_finding_regression() -> None:
    gap = operational_finding("opa", "timeout", "opa eval exceeded 60s")
    result = compare([], [gap])
    assert result.has_regressions is False
    assert [f["rule_id"] for f in result.new_findings] == ["scanner.opa.timeout"]
    assert [f["rule_id"] for f in result.evidence_gaps] == ["scanner.opa.timeout"]
    assert result.after_scan_complete is False


def test_became_failed_high_severity_is_a_regression() -> None:
    before = [_finding(FP_A, status="Passed")]
    after = [_finding(FP_A, status="Failed", severity="high")]
    result = compare(before, after)
    assert result.has_regressions is True
    assert [f["fingerprint"] for f in result.regressions] == [FP_A]
    assert [c["before_status"] for c in result.status_changes] == ["Passed"]
    assert [c["after_status"] for c in result.status_changes] == ["Failed"]


def test_became_failed_medium_goes_to_status_changes_only() -> None:
    before = [_finding(FP_A, status="Passed")]
    after = [_finding(FP_A, status="Failed", severity="medium")]
    result = compare(before, after)
    assert result.has_regressions is False
    assert len(result.status_changes) == 1


def test_unchanged_findings_preserved() -> None:
    item = _finding(FP_A, status="Failed", severity="low")
    result = compare([item], [dict(item)])
    assert [f["fingerprint"] for f in result.unchanged] == [FP_A]
    assert result.new_findings == []
    assert result.resolved == []


def test_disappeared_passing_finding_is_missing_not_resolved() -> None:
    before = [_finding(FP_A, status="Passed")]
    after = [_finding(FP_B, status="Passed", rule_id="OTHER")]
    result = compare(before, after)
    assert [f["fingerprint"] for f in result.missing_after] == [FP_A]
    assert result.resolved == []


def test_failed_finding_turned_skipped_is_not_resolved() -> None:
    before = [_finding(FP_A, status="Failed")]
    after = [_finding(FP_A, status="Skipped")]
    result = compare(before, after)
    assert result.resolved == []
    assert result.unconfirmed_resolved == []
    assert len(result.status_changes) == 1


def test_gap_pairing_reports_gap_once_and_keeps_evidence() -> None:
    gap = operational_finding("checkov", "timeout", "checkov exceeded time limit of 5s")
    result = compare([dict(gap)], [dict(gap)])
    assert result.unchanged == []
    assert [f["rule_id"] for f in result.evidence_gaps] == [gap["rule_id"]]
    assert result.resolved_confirmed is True
    assert result.after_scan_complete is False


def test_gap_to_pass_is_a_status_change_not_a_resolution() -> None:
    gap = operational_finding("checkov", "timeout", "checkov exceeded time limit of 5s")
    after = [_finding(gap["fingerprint"], status="Passed", rule_source="custom",
                      rule_id=gap["rule_id"], title=gap["title"], severity="unknown")]
    result = compare([dict(gap)], after)
    assert result.resolved == []
    assert len(result.status_changes) == 1
    assert result.evidence_gaps == []


def test_invalid_before_or_after_rejected() -> None:
    with pytest.raises(ContractValidationError):
        compare([minimal_finding(status="Secure")], [])
    with pytest.raises(ContractValidationError):
        compare([], [minimal_finding(rule_source="not_real")])
    with pytest.raises(ContractValidationError, match="must be a list"):
        compare("nope", [])  # type: ignore[arg-type]


def test_result_is_json_serializable() -> None:
    result = compare([], [_finding(FP_A, status="Failed", severity="critical")])
    payload = json.dumps(result.to_dict())
    assert '"has_regressions": true' in payload


def test_compare_is_deterministic() -> None:
    before = [_finding(FP_A, status="Failed"), _finding(FP_B, status="Failed")]
    after = [_finding(FP_B, status="Passed"), _finding(FP_C, status="Failed", severity="high")]
    first = compare(before, after).to_dict()
    second = compare(before, after).to_dict()
    assert first == second


def test_outputs_are_contract_valid() -> None:
    gap = operational_finding("checkov", "binary_missing", "checkov executable not found on PATH")
    before = [_finding(FP_A, status="Failed", severity="critical")]
    after = [gap, _finding(FP_B, status="Failed", severity="high")]
    result = compare(before, after)
    for finding in result.regressions + result.new_findings + result.evidence_gaps + result.unchanged:
        validate(finding, "finding")


def test_normalize_then_compare_roundtrip() -> None:
    raw_before = {
        "rule_source": "checkov", "check_id": "CKV_AWS_18", "status": "Failed",
        "severity": "high", "short_description": "logging", "resource": "aws_s3_bucket.a",
        "evidence": "no logging",
    }
    before = normalize([raw_before])
    after = normalize([dict(raw_before, status="Passed")])
    result = compare(before, after)
    assert [f["rule_id"] for f in result.resolved] == ["CKV_AWS_18"]
