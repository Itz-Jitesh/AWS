"""Terraform plan classification and stable plan digesting.

Canonicalization strategy for the plan digest: the entire plan document is
serialized as canonical JSON — ``json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=True)`` — and hashed with SHA-256.
Consequences:

* key order and whitespace never change the digest;
* any semantic change to the plan (including attribute values) changes it, so
  an approval bound to a digest is invalidated by any plan drift;
* only the digest is exposed — sensitive values inside the plan are hashed,
  never copied into summaries or evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from .contracts import validate
from .errors import InvalidPlanError

SCHEMA_VERSION = "1.0.0"
ACTIONS = ("create", "update", "delete", "read", "no-op")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")


def loads_plan(text: str) -> dict[str, Any]:
    """Parse a ``terraform show -json`` document, failing closed on garbage."""
    if not isinstance(text, str):
        raise InvalidPlanError("plan input must be a string of JSON")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidPlanError(f"plan JSON is not parseable: {exc}") from exc
    if not isinstance(parsed, dict):
        raise InvalidPlanError(
            f"plan JSON must be an object, got {type(parsed).__name__}"
        )
    return parsed


def plan_digest(plan_json: Any) -> str:
    """Return the stable SHA-256 digest of a plan document."""
    if not isinstance(plan_json, dict):
        raise InvalidPlanError(
            f"plan JSON must be an object, got {type(plan_json).__name__}"
        )
    canonical = json.dumps(
        plan_json, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_digest(plan_json: Any, expected: str | None) -> bool:
    """Return True only when ``expected`` is a well-formed matching digest."""
    if not isinstance(expected, str) or not _DIGEST_RE.fullmatch(expected):
        return False
    return hmac.compare_digest(plan_digest(plan_json), expected)


def classify_plan(plan_json: Any) -> dict[str, Any]:
    """Classify plan resource changes into a contract-valid PlanSummary."""
    if not isinstance(plan_json, dict):
        raise InvalidPlanError(
            f"plan JSON must be an object, got {type(plan_json).__name__}"
        )
    raw_changes = plan_json.get("resource_changes", [])
    if raw_changes is None:
        raw_changes = []
    if not isinstance(raw_changes, list):
        raise InvalidPlanError("resource_changes must be an array")

    counts = {"create": 0, "update": 0, "replace": 0, "destroy": 0}
    destructive: list[dict[str, Any]] = []

    for index, change in enumerate(raw_changes):
        if not isinstance(change, dict):
            raise InvalidPlanError(f"resource_changes[{index}] must be an object")
        address = change.get("address")
        if not isinstance(address, str) or not address:
            raise InvalidPlanError(f"resource_changes[{index}] is missing an address")
        if change.get("mode") == "data":
            continue
        body = change.get("change")
        if not isinstance(body, dict):
            raise InvalidPlanError(
                f"resource_changes[{index}] ({address}) is missing change data"
            )
        actions = body.get("actions")
        if not isinstance(actions, list) or not actions:
            raise InvalidPlanError(
                f"resource_changes[{index}] ({address}) has no actions"
            )
        for action in actions:
            if action not in ACTIONS:
                raise InvalidPlanError(
                    f"resource_changes[{index}] ({address}) has unsupported action {action!r}"
                )

        action_set = set(actions)
        reason = change.get("action_reason", body.get("action_reason"))
        reason_suffix = (
            f" (terraform action_reason: {reason})"
            if isinstance(reason, str) and reason
            else ""
        )

        if "delete" in action_set and "create" in action_set:
            counts["replace"] += 1
            destructive.append(
                {
                    "address": address,
                    "actions": list(actions),
                    "risk": "high",
                    "reason": (
                        f"terraform will destroy and recreate {address}; replacement "
                        "is destructive and may cause downtime or data loss"
                        f"{reason_suffix}"
                    ),
                }
            )
        elif "delete" in action_set:
            counts["destroy"] += 1
            destructive.append(
                {
                    "address": address,
                    "actions": list(actions),
                    "risk": "high",
                    "reason": f"terraform will permanently delete {address}{reason_suffix}",
                }
            )
        elif "create" in action_set:
            counts["create"] += 1
        elif "update" in action_set:
            counts["update"] += 1

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "plan_digest": plan_digest(plan_json),
        **counts,
        "destructive_actions": destructive,
        "has_changes": any(counts.values()),
    }
    validate(summary, "plan-summary")
    return summary
