"""Plan classification and digest tests."""

from __future__ import annotations

import hashlib
import json

import pytest

from audit.contracts import validate
from audit.errors import InvalidPlanError
from audit.plan import classify_plan, loads_plan, plan_digest, verify_digest

from .conftest import load_fixture


def test_dod_fixture_s3_delete_and_iam_update() -> None:
    plan = load_fixture("plan_s3_delete_iam_update.json")
    summary = classify_plan(plan)
    validate(summary, "plan-summary")
    assert summary["destroy"] == 1
    assert summary["update"] == 1
    assert summary["create"] == 0
    assert summary["replace"] == 0
    assert summary["has_changes"] is True

    [destructive] = summary["destructive_actions"]
    assert destructive["address"] == "aws_s3_bucket.public_data"
    assert destructive["actions"] == ["delete"]
    assert destructive["risk"] == "high"
    assert "permanently delete" in destructive["reason"]
    assert summary["plan_digest"] == plan_digest(plan)


def test_plan_values_never_copied_into_summary() -> None:
    plan = load_fixture("plan_s3_delete_iam_update.json")
    summary_json = json.dumps(classify_plan(plan))
    assert "REDACTED-FIXTURE-VALUE" not in summary_json
    assert "public-read" not in summary_json


def test_replacement_is_not_treated_as_update() -> None:
    plan = load_fixture("plan_replace.json")
    summary = classify_plan(plan)
    assert summary["replace"] == 1
    assert summary["update"] == 0
    assert summary["create"] == 1
    [destructive] = [
        entry for entry in summary["destructive_actions"] if entry["address"] == "aws_s3_bucket.logs"
    ]
    assert set(destructive["actions"]) == {"delete", "create"}
    assert destructive["risk"] == "high"
    assert "destroy and recreate" in destructive["reason"]
    assert "delete_because_cannot_update" in destructive["reason"]


def test_data_sources_and_noop_do_not_count() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_s3_bucket.keep",
                "mode": "managed",
                "change": {"actions": ["no-op"]},
            },
            {
                "address": "data.aws_ami.base",
                "mode": "data",
                "change": {"actions": ["read"]},
            },
        ]
    }
    summary = classify_plan(plan)
    assert summary["has_changes"] is False
    assert summary["destructive_actions"] == []
    assert summary["create"] == summary["destroy"] == summary["replace"] == summary["update"] == 0


def test_empty_plan_is_valid_and_has_no_changes() -> None:
    summary = classify_plan({})
    assert summary["has_changes"] is False
    assert summary["plan_digest"] == hashlib.sha256(b"{}").hexdigest()


def test_digest_is_key_order_independent() -> None:
    plan_a = {
        "format_version": "1.2",
        "resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": ["update"]}}],
    }
    plan_b = {
        "resource_changes": [{"change": {"actions": ["update"]}, "address": "aws_s3_bucket.x"}],
        "format_version": "1.2",
    }
    assert plan_digest(plan_a) == plan_digest(plan_b)


def test_digest_is_whitespace_independent() -> None:
    compact = '{"a":1,"b":{"c":2}}'
    spaced = '{ "a" : 1 , "b" : { "c" : 2 } }'
    assert plan_digest(json.loads(compact)) == plan_digest(json.loads(spaced))


def test_digest_changes_when_attribute_value_changes() -> None:
    plan_a = {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"after": {"bucket": "one"}}}]}
    plan_b = {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"after": {"bucket": "two"}}}]}
    assert plan_digest(plan_a) != plan_digest(plan_b)


def test_digest_changes_when_actions_change() -> None:
    plan_a = {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": ["update"]}}]}
    plan_b = {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": ["delete"]}}]}
    assert plan_digest(plan_a) != plan_digest(plan_b)


def test_verify_digest_accepts_only_exact_match() -> None:
    plan = {"resource_changes": []}
    digest = plan_digest(plan)
    assert verify_digest(plan, digest) is True
    assert verify_digest(plan, "a" * 64) is False
    assert verify_digest(plan, None) is False
    assert verify_digest(plan, "") is False
    assert verify_digest(plan, digest.upper()) is False
    assert verify_digest(plan, "not-a-digest") is False


def test_verify_digest_false_when_plan_drifts_after_approval() -> None:
    approved = {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": ["update"]}}]}
    drifted = {
        "resource_changes": [
            {"address": "aws_s3_bucket.x", "change": {"actions": ["delete"]}}
        ]
    }
    assert verify_digest(drifted, plan_digest(approved)) is False


@pytest.mark.parametrize(
    "bad_plan",
    [
        "not json at all",
        '"just a string"',
        "[1, 2, 3]",
        42,
        {"resource_changes": "nope"},
        {"resource_changes": [{"change": {"actions": ["update"]}}]},
        {"resource_changes": [{"address": "aws_s3_bucket.x"}]},
        {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": []}}]},
        {"resource_changes": [{"address": "aws_s3_bucket.x", "change": {"actions": ["forget"]}}]},
        {"resource_changes": [{"address": "", "change": {"actions": ["update"]}}]},
        {"resource_changes": ["string-entry"]},
    ],
)
def test_invalid_plan_json_raises(bad_plan) -> None:
    with pytest.raises(InvalidPlanError):
        classify_plan(bad_plan)


def test_loads_plan_raises_on_garbage() -> None:
    with pytest.raises(InvalidPlanError, match="not parseable"):
        loads_plan("{broken")
    with pytest.raises(InvalidPlanError, match="must be an object"):
        loads_plan("[1]")


def test_plan_digest_requires_object() -> None:
    with pytest.raises(InvalidPlanError):
        plan_digest(["list"])  # type: ignore[arg-type]


def test_counts_stable_when_change_order_shuffled_but_digest_is_not() -> None:
    plan = load_fixture("plan_s3_delete_iam_update.json")
    first = classify_plan(plan)
    shuffled = {"terraform_version": plan["terraform_version"], **{"format_version": plan["format_version"], **{"resource_changes": list(reversed(plan["resource_changes"]))}}}
    second = classify_plan(shuffled)
    assert first["plan_digest"] != second["plan_digest"]
    assert second["destroy"] == first["destroy"]
    assert second["update"] == first["update"]
