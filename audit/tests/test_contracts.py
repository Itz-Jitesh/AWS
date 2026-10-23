"""Contract loading and strict validation tests."""

from __future__ import annotations

import pytest

from audit.contracts import (
    SCHEMA_NAMES,
    contracts_dir,
    is_valid,
    load_schema,
    validate,
    validate_all,
)
from audit.errors import ContractValidationError

from .conftest import minimal_finding


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_all_shared_schemas_load_and_are_valid(name: str) -> None:
    schema = load_schema(name)
    assert schema["properties"]["schema_version"]["const"] == "1.0.0"
    assert (contracts_dir() / f"{name}.schema.json").is_file()


def test_unknown_contract_name_rejected() -> None:
    with pytest.raises(ContractValidationError, match="unknown contract"):
        load_schema("nonsense")


def test_minimal_finding_is_valid() -> None:
    validate(minimal_finding(), "finding")
    assert is_valid(minimal_finding(), "finding")


def test_finding_rejects_additional_properties() -> None:
    with pytest.raises(ContractValidationError):
        validate(minimal_finding(extra_field="nope"), "finding")


def test_finding_rejects_schema_version_bump_without_contract_change() -> None:
    with pytest.raises(ContractValidationError, match="schema_version"):
        validate(minimal_finding(schema_version="1.0.1"), "finding")


def test_finding_rejects_missing_evidence() -> None:
    bad = minimal_finding()
    del bad["evidence"]
    with pytest.raises(ContractValidationError, match="evidence"):
        validate(bad, "finding")


def test_finding_rejects_bad_status_enum() -> None:
    with pytest.raises(ContractValidationError, match="status"):
        validate(minimal_finding(status="Secure"), "finding")


def test_finding_rejects_bad_rule_source() -> None:
    with pytest.raises(ContractValidationError, match="rule_source"):
        validate(minimal_finding(rule_source="fabricated_scanner"), "finding")


def test_validate_all_reports_item_index() -> None:
    good = minimal_finding()
    bad = minimal_finding(status="Bogus")
    with pytest.raises(ContractValidationError, match=r"item 1"):
        validate_all([good, bad], "finding")


def test_plan_summary_contract_shape() -> None:
    summary = {
        "schema_version": "1.0.0",
        "plan_digest": "b" * 64,
        "create": 0,
        "update": 1,
        "replace": 0,
        "destroy": 1,
        "destructive_actions": [
            {
                "address": "aws_s3_bucket.public",
                "actions": ["delete"],
                "risk": "high",
                "reason": "terraform will permanently delete aws_s3_bucket.public",
            }
        ],
        "has_changes": True,
    }
    validate(summary, "plan-summary")
    summary["destructive_actions"][0]["risk"] = "catastrophic"
    with pytest.raises(ContractValidationError, match="risk"):
        validate(summary, "plan-summary")


def test_requirement_contract_shape() -> None:
    requirement = {
        "schema_version": "1.0.0",
        "requirement_id": "req-1",
        "text": "Preserve the bucket",
        "mandatory": True,
        "status": "Unverified",
        "evidence": ["plan digest abcd"],
    }
    validate(requirement, "requirement")
    requirement["status"] = "ProbablyFine"
    with pytest.raises(ContractValidationError, match="status"):
        validate(requirement, "requirement")


def test_contracts_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PLANPROOF_CONTRACTS_DIR", str(tmp_path))
    assert contracts_dir() == tmp_path
    with pytest.raises(ContractValidationError, match="shared schema not found"):
        load_schema("finding")
