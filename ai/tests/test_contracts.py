import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from planproof_ai.contracts import (
    CheckRun,
    CheckStatus,
    DestructiveAction,
    Finding,
    Patch,
    PlanAction,
    PlanSummary,
    Requirement,
    RequirementStatus,
    RiskLevel,
    RuleSource,
    Severity,
)
from planproof_ai.testing import make_check, make_plan_summary, make_requirement

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"

SCHEMAS = {
    "checkrun": "checkrun.schema.json",
    "finding": "finding.schema.json",
    "requirement": "requirement.schema.json",
    "patch": "patch.schema.json",
    "plan-summary": "plan-summary.schema.json",
}


def validate(name: str, payload: dict) -> None:
    schema_path = CONTRACTS / SCHEMAS[name]
    assert schema_path.exists(), f"frozen contract missing: {schema_path}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, f"{name} payload violates contract: {[e.message for e in errors]}"


def test_all_contract_files_present():
    for filename in SCHEMAS.values():
        assert (CONTRACTS / filename).exists()


def test_check_run_validates():
    check = make_check("fmt", CheckStatus.FAILED, summary="fmt issues", exit_code=3)
    validate("checkrun", check.contract_dump())


def test_check_run_invalid_status_rejected():
    with pytest.raises(ValueError):
        make_check("fmt", "Secure")


def test_finding_validates():
    finding = Finding(
        finding_id="f-1",
        rule_source=RuleSource.CHECKOV,
        rule_id="CKV_AWS_18",
        severity=Severity.HIGH,
        status=CheckStatus.FAILED,
        title="S3 access logging disabled",
        evidence="resource aws_s3_bucket.b has no access logging",
        remediation="Enable access logging",
        fingerprint="abc123",
        resource_address="aws_s3_bucket.b",
        file_path="main.tf",
        line_start=1,
    )
    validate("finding", finding.contract_dump())


def test_requirement_validates():
    req = make_requirement("bucket must stay private", status=RequirementStatus.UNVERIFIED)
    validate("requirement", req.contract_dump())


def test_requirement_bad_status_rejected():
    with pytest.raises(ValueError):
        make_requirement("x", status="Secure")


def test_patch_validates():
    patch = Patch(
        patch_id="patch-1",
        unified_diff="--- a/main.tf\n+++ b/main.tf\n@@ -1,1 +1,1 @@\n-x\n+y\n",
        rationale="minimal change",
        files_changed=["main.tf"],
        base_digest="a" * 64,
        model_id="mock-llm-v1",
    )
    validate("patch", patch.contract_dump())


def test_patch_bad_digest_rejected():
    with pytest.raises(ValueError):
        Patch(
            patch_id="p",
            unified_diff="--- a/main.tf\n+++ b/main.tf\n@@ -1 +1 @@\n-x\n+y\n",
            rationale="r",
            files_changed=["main.tf"],
            base_digest="not-a-digest",
        )


def test_plan_summary_validates():
    summary = PlanSummary(
        plan_digest="b" * 64,
        create=1,
        update=1,
        replace=0,
        destroy=1,
        destructive_actions=[
            DestructiveAction(
                address="aws_s3_bucket.b",
                actions=[PlanAction.DELETE],
                risk=RiskLevel.HIGH,
                reason="replacement",
            )
        ],
        has_changes=True,
    )
    validate("plan-summary", summary.contract_dump())


def test_plan_summary_helper_validates():
    validate("plan-summary", make_plan_summary(destroy=1).contract_dump())


def test_contract_models_forbid_extra_fields():
    with pytest.raises(ValueError):
        CheckRun(
            check_id="x",
            tool="terraform",
            status=CheckStatus.PASSED,
            started_at="2026-01-01T00:00:00Z",
            duration_ms=1,
            summary="ok",
            unexpected_field=True,
        )
