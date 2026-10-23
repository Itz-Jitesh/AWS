"""Finding normalization tests."""

from __future__ import annotations

import pytest

from audit.contracts import validate
from audit.errors import ContractValidationError, NormalizationError
from audit.normalize import normalize
from audit.operational import operational_finding


def test_checkov_style_record_normalized() -> None:
    raw = {
        "rule_source": "checkov",
        "check_id": "CKV_AWS_18",
        "status": "Failed",
        "severity": "HIGH",
        "short_description": "S3 access logging disabled",
        "resource": "aws_s3_bucket.logs",
        "file_path": "main.tf",
        "file_line_range": [3, 9],
        "evidence": "aws_s3_bucket.logs has no access_logging block",
    }
    [finding] = normalize([raw])
    validate(finding, "finding")
    assert finding["rule_id"] == "CKV_AWS_18"
    assert finding["severity"] == "high"
    assert finding["line_start"] == 3
    assert finding["resource_address"] == "aws_s3_bucket.logs"
    assert finding["status"] == "Failed"
    assert finding["evidence"]


def test_evidence_derived_only_from_concrete_fields() -> None:
    raw = {
        "rule_source": "opa",
        "rule_id": "TF_IAM_WILDCARD_RESOURCE",
        "status": "Failed",
        "title": "IAM wildcard",
        "resource_address": "aws_iam_policy.wide",
        "description": "planned policy allows Resource *",
    }
    [finding] = normalize([raw])
    assert "planned policy allows Resource *" in finding["evidence"]
    assert "aws_iam_policy.wide" in finding["evidence"]


def test_missing_evidence_is_rejected_not_fabricated() -> None:
    raw = {
        "rule_source": "checkov",
        "rule_id": "CKV_AWS_1",
        "status": "Failed",
        "title": "no evidence anywhere",
    }
    with pytest.raises(NormalizationError, match="refusing to fabricate"):
        normalize([raw])


@pytest.mark.parametrize("missing", ["rule_source", "rule_id", "status"])
def test_required_fields_enforced(missing: str) -> None:
    raw = {
        "rule_source": "checkov",
        "rule_id": "CKV_AWS_1",
        "status": "Failed",
        "title": "t",
        "evidence": "e",
    }
    del raw[missing]
    with pytest.raises(NormalizationError):
        normalize([raw])


def test_unknown_rule_source_rejected() -> None:
    raw = {
        "rule_source": "made_up_scanner",
        "rule_id": "X1",
        "status": "Failed",
        "title": "t",
        "evidence": "e",
    }
    with pytest.raises(NormalizationError, match="rule_source"):
        normalize([raw])


def test_bad_status_rejected() -> None:
    raw = {
        "rule_source": "checkov",
        "rule_id": "X1",
        "status": "LooksFine",
        "title": "t",
        "evidence": "e",
    }
    with pytest.raises(NormalizationError, match="status"):
        normalize([raw])


def test_unable_to_verify_state_preserved() -> None:
    raw = {
        "rule_source": "custom",
        "rule_id": "scanner.checkov.timeout",
        "status": "UnableToVerify",
        "severity": "unknown",
        "title": "checkov timed out",
        "evidence": "checkov exceeded time limit of 120s",
    }
    [finding] = normalize([raw])
    assert finding["status"] == "UnableToVerify"


def test_missing_severity_becomes_unknown() -> None:
    raw = {
        "rule_source": "opa",
        "rule_id": "R1",
        "status": "Failed",
        "title": "t",
        "evidence": "e",
    }
    [finding] = normalize([raw])
    assert finding["severity"] == "unknown"


def test_unrecognised_severity_rejected() -> None:
    raw = {
        "rule_source": "opa",
        "rule_id": "R1",
        "status": "Failed",
        "severity": "apocalyptic",
        "title": "t",
        "evidence": "e",
    }
    with pytest.raises(NormalizationError, match="severity"):
        normalize([raw])


def test_fingerprint_is_deterministic_and_address_sensitive() -> None:
    base = {
        "rule_source": "checkov",
        "rule_id": "CKV_AWS_18",
        "status": "Failed",
        "title": "logging",
        "resource_address": "aws_s3_bucket.a",
        "evidence": "missing logging",
    }
    first = normalize([dict(base)])[0]
    second = normalize([dict(base)])[0]
    assert first["fingerprint"] == second["fingerprint"]
    assert first["finding_id"] == second["finding_id"]
    other = dict(base, resource_address="aws_s3_bucket.b")
    assert normalize([other])[0]["fingerprint"] != first["fingerprint"]


def test_secret_in_evidence_is_redacted() -> None:
    raw = {
        "rule_source": "terraform",
        "rule_id": "TF_OUTPUT_SECRET",
        "status": "Failed",
        "title": "sensitive output",
        "evidence": "output value secret_access_key = wJalrXUtnFEMIEXAMPLEKEY",
    }
    [finding] = normalize([raw])
    assert "wJalrXUtnFEMIEXAMPLEKEY" not in finding["evidence"]
    assert "[REDACTED]" in finding["evidence"]


def test_normalize_rejects_scalar_input() -> None:
    with pytest.raises(NormalizationError, match="iterable"):
        normalize({"rule_id": "x"})  # type: ignore[arg-type]


def test_normalize_rejects_non_object_item() -> None:
    with pytest.raises(NormalizationError, match="not an object"):
        normalize(["oops"])  # type: ignore[list-item]


def test_output_fails_contract_when_schema_version_wrong() -> None:
    raw = {
        "rule_source": "checkov",
        "rule_id": "X",
        "status": "Failed",
        "title": "t",
        "evidence": "e",
        "schema_version": "9.9.9",
    }
    [finding] = normalize([raw])
    assert finding["schema_version"] == "1.0.0"
    with pytest.raises(ContractValidationError):
        validate(dict(finding, schema_version="9.9.9"), "finding")


def test_operational_finding_is_custom_and_unable_to_verify() -> None:
    finding = operational_finding("checkov", "binary_missing", "checkov executable not found on PATH")
    validate(finding, "finding")
    assert finding["rule_source"] == "custom"
    assert finding["rule_id"] == "scanner.checkov.binary_missing"
    assert finding["status"] == "UnableToVerify"
    assert finding["severity"] == "unknown"
    assert "not found" in str(finding["evidence"])


def test_operational_finding_requires_evidence() -> None:
    with pytest.raises(NormalizationError, match="evidence"):
        operational_finding("opa", "eval_failed", "   ")


def test_operational_finding_rejects_bad_kind() -> None:
    with pytest.raises(NormalizationError, match="kind"):
        operational_finding("opa", "Not A Kind", "evidence")
