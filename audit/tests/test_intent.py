"""Intent check tests: conservative statuses with real plan/diff evidence."""

from __future__ import annotations

import json

import pytest

from audit.contracts import validate
from audit.errors import ContractValidationError
from audit.intent import check_intent
from audit.plan import classify_plan

from .conftest import load_fixture, load_fixture_text


def requirement(text: str, **overrides) -> dict:
    base = {
        "schema_version": "1.0.0",
        "requirement_id": "req-1",
        "text": text,
        "mandatory": True,
        "status": "Unverified",
    }
    base.update(overrides)
    return base


def dod_summary() -> dict:
    return classify_plan(load_fixture("plan_s3_delete_iam_update.json"))


def clean_summary() -> dict:
    return classify_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.logs",
                    "mode": "managed",
                    "change": {"actions": ["no-op"]},
                }
            ]
        }
    )


def destroy_role_summary() -> dict:
    return classify_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_iam_role.y",
                    "mode": "managed",
                    "change": {"actions": ["delete"]},
                }
            ]
        }
    )


def test_explicit_address_destruction_is_violated() -> None:
    [req] = check_intent(
        [requirement("Preserve aws_s3_bucket.public_data without deleting it.")],
        "",
        dod_summary(),
    )
    validate(req, "requirement")
    assert req["status"] == "Violated"
    assert any("permanently delete" in e for e in req["evidence"])
    assert req["mandatory"] is True
    assert req["evidence"], "violations must carry evidence"


def test_preserved_resource_with_clean_plan_is_satisfied() -> None:
    [req] = check_intent(
        [requirement("Keep aws_s3_bucket.logs unchanged.")],
        "",
        clean_summary(),
    )
    assert req["status"] == "Satisfied"
    assert req["evidence"], "satisfied must carry evidence"
    assert any("plan" in e for e in req["evidence"])


def test_unnamed_target_clean_plan_satisfied() -> None:
    [req] = check_intent([requirement("Do not delete anything.")], "", clean_summary())
    assert req["status"] == "Satisfied"


def test_unnamed_target_with_destructive_plan_is_unverified() -> None:
    [req] = check_intent([requirement("Preserve it without deleting.")], "", dod_summary())
    assert req["status"] == "Unverified"
    assert req["evidence"], "unverified should explain what is known"


def test_type_only_match_is_unverified_not_satisfied() -> None:
    [req] = check_intent([requirement("Keep the bucket.")], "", dod_summary())
    assert req["status"] == "Unverified"
    assert any("aws_s3_bucket.public_data" in e for e in req["evidence"])


def test_type_only_no_type_match_is_satisfied() -> None:
    [req] = check_intent([requirement("Keep the bucket.")], "", destroy_role_summary())
    assert req["status"] == "Satisfied"
    assert any("aws_s3_bucket" in e for e in req["evidence"])


def test_diff_removal_violates_even_with_clean_plan() -> None:
    [req] = check_intent(
        [requirement("Preserve aws_s3_bucket.public_data.")],
        load_fixture_text("diff_delete_bucket.patch"),
        clean_summary(),
    )
    assert req["status"] == "Violated"
    assert any("diff removes resource block" in e for e in req["evidence"])


def test_security_config_text_alone_is_never_satisfied() -> None:
    [req] = check_intent(
        [requirement("Make the bucket private.")],
        load_fixture_text("diff_make_private.patch"),
        dod_summary(),
    )
    validate(req, "requirement")
    assert req["status"] == "Unverified"
    assert any("diff" in e for e in req["evidence"])
    assert "does not prove" in req["notes"]


def test_added_public_acl_violates_access_requirement() -> None:
    [req] = check_intent(
        [requirement("Make sure nothing is publicly exposed.")],
        load_fixture_text("diff_add_public_acl.patch"),
        clean_summary(),
    )
    assert req["status"] == "Violated"
    assert any("public ACL" in e for e in req["evidence"])


def test_no_evidence_for_access_requirement_is_unverified() -> None:
    [req] = check_intent(
        [requirement("Restrict public access on all buckets.")], "", clean_summary()
    )
    assert req["status"] == "Unverified"


def test_no_changes_requirement_satisfied_only_when_nothing_changes() -> None:
    [req] = check_intent([requirement("Make no changes to the repository.")], "", clean_summary())
    assert req["status"] == "Satisfied"
    [req2] = check_intent(
        [requirement("Make no changes to the repository.")],
        load_fixture_text("diff_make_private.patch"),
        dod_summary(),
    )
    assert req2["status"] == "Violated"


def test_unknown_goal_is_unverified_without_fabricated_evidence() -> None:
    [req] = check_intent(
        [requirement("Use cheaper instance types across the estate.")], "", clean_summary()
    )
    assert req["status"] == "Unverified"
    assert req["evidence"] == []
    assert "no deterministic rule" in req["notes"]


def test_compound_requirement_worst_status_wins() -> None:
    [req] = check_intent(
        [requirement("Make aws_s3_bucket.public_data private without deleting it.")],
        load_fixture_text("diff_make_private.patch"),
        dod_summary(),
    )
    validate(req, "requirement")
    assert req["status"] == "Violated"
    assert len(req["evidence"]) >= 2


def test_input_evidence_is_redacted_and_preserved() -> None:
    [req] = check_intent(
        [requirement("Preserve aws_s3_bucket.logs.", evidence=["token = abc123secretvalue"])],
        "",
        clean_summary(),
    )
    assert "abc123secretvalue" not in json.dumps(req["evidence"])
    assert any("[REDACTED]" in e for e in req["evidence"])


def test_inputs_are_not_mutated() -> None:
    original = requirement("Make the bucket private.")
    snapshot = json.dumps(original, sort_keys=True)
    check_intent([original], load_fixture_text("diff_make_private.patch"), clean_summary())
    assert json.dumps(original, sort_keys=True) == snapshot


def test_all_outputs_are_contract_valid() -> None:
    outputs = check_intent(
        [
            requirement("Preserve aws_s3_bucket.public_data."),
            requirement("Make it private."),
            requirement("No changes."),
            requirement("Something we cannot verify."),
        ],
        load_fixture_text("diff_make_private.patch"),
        dod_summary(),
    )
    for req in outputs:
        validate(req, "requirement")
        assert req["status"] in {"Satisfied", "Unverified", "Violated"}


def test_empty_requirements_return_empty_list() -> None:
    assert check_intent([], "", clean_summary()) == []


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(ContractValidationError):
        check_intent("scalar", "", clean_summary())  # type: ignore[arg-type]
    with pytest.raises(ContractValidationError):
        check_intent([{"schema_version": "1.0.0"}], "", clean_summary())
    with pytest.raises(ContractValidationError):
        check_intent([requirement("keep it")], "", {"schema_version": "1.0.0"})
    with pytest.raises(ContractValidationError):
        check_intent([requirement("keep it")], 42, clean_summary())  # type: ignore[arg-type]
