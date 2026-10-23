"""Conservative intent checking for natural-language requirements.

``check_intent(requirements, diff, plan_summary) -> Requirement[]`` decides
each requirement's final status from deterministic evidence only:

* plan evidence — ``PlanSummary`` destructive actions, counts, and digest;
* source evidence — the proposed unified diff.

Rules implemented (each may apply; the worst status wins):

1. **Preservation** — an explicitly named resource that the plan destroys or
   the diff removes is ``Violated``. ``Satisfied`` requires positive plan
   evidence (the exhaustive destructive list omits it, or the plan contains
   no destructive actions at all and the diff removes no blocks). A type-only
   or unattributable target that could be among destructive actions is
   ``Unverified``.
2. **Public/private configuration** — contrary diff evidence is ``Violated``.
   Supporting config text alone is NEVER ``Satisfied``: source text does not
   prove the resulting infrastructure is private, so it stays ``Unverified``.
3. **No-changes requirements** — ``Satisfied`` only when the diff is empty
   and the plan reports no changes.
4. Anything else — ``Unverified``.

``Satisfied`` is never emitted without concrete evidence strings.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from .contracts import validate, validate_all
from .errors import ContractValidationError
from .redact import redact_text

_RANK = {"Satisfied": 0, "Unverified": 1, "Violated": 2}

_PRESERVE_RE = re.compile(
    r"(?i)\b(?:preserv\w*|keep|retai\w*|protect\w*|do not delete|don't delete|"
    r"without deleting|do not remove|don't remove|no deletion|"
    r"must not\s+(?:be\s+)?(?:deleted|removed|replaced)|must not replace)\b"
)
_NO_CHANGES_RE = re.compile(r"(?i)\b(?:no changes?|without changes|unchanged|no modifications?)\b")
_PRIVATE_RE = re.compile(
    r"(?i)\b(?:private|public|publicly accessible|public access|block public|exposed?)\b"
)
_ADDRESS_RE = re.compile(
    r"(?:module\.[A-Za-z0-9_-]+\.)*aws_[a-z0-9_]+\.[A-Za-z0-9_]+(?:\[[^\]]+\])*"
)
_REMOVED_BLOCK_RE = re.compile(r'(?m)^-\s*resource\s+"([^"]+)"\s+"([^"]+)"')
_ADDED_PUBLIC_ACL_RE = re.compile(
    r'(?m)^\+(?!\+\+)\s*acl\s*=\s*"(public-read|public-read-write|authenticated-read)"'
)
_ADDED_PRIVATE_ACL_RE = re.compile(r'(?m)^\+(?!\+\+)\s*acl\s*=\s*"private"')
_ADDED_PAB_FALSE_RE = re.compile(
    r"(?m)^\+(?!\+\+)\s*block_public_(?:acls|policy|ignore_public_acls|restrict_public_buckets)\s*=\s*false"
)
_ADDED_PAB_TRUE_RE = re.compile(
    r"(?m)^\+(?!\+\+)\s*block_public_(?:acls|policy|ignore_public_acls|restrict_public_buckets)\s*=\s*true"
)
_REMOVED_PAB_TRUE_RE = re.compile(
    r"(?m)^-\s*block_public_(?:acls|policy|ignore_public_acls|restrict_public_buckets)\s*=\s*true"
)
_ADDED_PAB_RESOURCE_RE = re.compile(r'(?m)^\+(?!\+\+)\s*resource\s+"aws_s3_bucket_public_access_block"')

_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("s3 bucket", "aws_s3_bucket"),
    ("bucket", "aws_s3_bucket"),
    ("iam role", "aws_iam_role"),
    ("role", "aws_iam_role"),
    ("iam policy", "aws_iam_policy"),
    ("policy", "aws_iam_policy"),
    ("security group", "aws_security_group"),
    ("instance", "aws_instance"),
    ("server", "aws_instance"),
    ("database", "aws_db_instance"),
    ("db instance", "aws_db_instance"),
    ("table", "aws_dynamodb_table"),
    ("queue", "aws_sqs_queue"),
    ("topic", "aws_sns_topic"),
    ("lambda", "aws_lambda_function"),
    ("function", "aws_lambda_function"),
)


def check_intent(
    requirements: Iterable[Mapping[str, Any]],
    diff: str,
    plan_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return requirements with final status, evidence, and notes."""
    if requirements is None or isinstance(requirements, (str, bytes, Mapping)):
        raise ContractValidationError("requirements must be a list of Requirement objects")
    items = list(requirements)
    validate_all(items, "requirement")
    if not isinstance(plan_summary, Mapping):
        raise ContractValidationError("plan_summary must be a PlanSummary object")
    validate(plan_summary, "plan-summary")
    if diff is None:
        diff = ""
    if not isinstance(diff, str):
        raise ContractValidationError("diff must be a string")

    outputs: list[dict[str, Any]] = []
    for requirement in items:
        updated = copy.deepcopy(requirement)
        status, evidence, notes = _evaluate(updated["text"], diff, plan_summary)
        merged_evidence = list(dict.fromkeys(list(updated.get("evidence") or []) + evidence))
        merged_evidence = [redact_text(str(e)) for e in merged_evidence if str(e).strip()]
        updated["evidence"] = merged_evidence
        existing_note = updated.get("notes")
        updated["notes"] = "; ".join(n for n in (existing_note, notes) if n)
        updated["status"] = status
        validate(updated, "requirement")
        outputs.append(updated)
    return outputs


def _evaluate(
    text: str, diff: str, summary: Mapping[str, Any]
) -> tuple[str, list[str], str]:
    outcomes: list[tuple[str, list[str], str]] = []
    for applies, evaluate in (
        (_NO_CHANGES_RE.search(text), _evaluate_no_changes),
        (_PRESERVE_RE.search(text), _evaluate_preservation),
        (_PRIVATE_RE.search(text), _evaluate_public_private),
    ):
        if applies:
            outcomes.append(evaluate(text, diff, summary))
    if not outcomes:
        return (
            "Unverified",
            [],
            "no deterministic rule can verify this requirement from plan or diff evidence",
        )
    status = max((outcome[0] for outcome in outcomes), key=lambda s: _RANK[s])
    evidence = [item for outcome in outcomes for item in outcome[1]]
    notes = " | ".join(outcome[2] for outcome in outcomes if outcome[2])
    return status, list(dict.fromkeys(evidence)), notes


def _digest_ref(summary: Mapping[str, Any]) -> str:
    return f"plan {str(summary['plan_digest'])[:12]}"


def _matches(address: str, candidates: Iterable[str]) -> bool:
    for candidate in candidates:
        if address == candidate:
            return True
        if address.startswith(candidate + "."):
            return True
        if address.endswith("." + candidate) or candidate.endswith("." + address):
            return True
    return False


def _removed_blocks(diff: str) -> list[str]:
    return [f"{match.group(1)}.{match.group(2)}" for match in _REMOVED_BLOCK_RE.finditer(diff)]


def _extract_addresses(text: str) -> list[str]:
    return list(dict.fromkeys(_ADDRESS_RE.findall(text)))


def _extract_types(text: str) -> list[str]:
    lowered = text.lower()
    types: list[str] = []
    for phrase, tf_type in _TYPE_HINTS:
        if re.search(rf"(?i)\b{re.escape(phrase)}\b", lowered) and tf_type not in types:
            types.append(tf_type)
    return types


def _evaluate_no_changes(
    text: str, diff: str, summary: Mapping[str, Any]
) -> tuple[str, list[str], str]:
    changes = bool(diff.strip()) or bool(summary["has_changes"])
    if changes:
        evidence = [
            f"{_digest_ref(summary)}: create={summary['create']} update={summary['update']} "
            f"replace={summary['replace']} destroy={summary['destroy']}",
        ]
        if diff.strip():
            evidence.append("proposed diff is not empty")
        return "Violated", evidence, "changes exist although the requirement asks for none"
    return (
        "Satisfied",
        [
            f"{_digest_ref(summary)}: has_changes=false",
            "proposed diff is empty",
        ],
        "",
    )


def _evaluate_preservation(
    text: str, diff: str, summary: Mapping[str, Any]
) -> tuple[str, list[str], str]:
    addresses = _extract_addresses(text)
    types = _extract_types(text)
    destructive = list(summary["destructive_actions"])
    destructive_addresses = [entry["address"] for entry in destructive]
    removed = _removed_blocks(diff)

    violations: list[str] = []
    for address in addresses:
        for entry in destructive:
            if _matches(address, [entry["address"]]):
                violations.append(f"{_digest_ref(summary)}: {entry['reason']}")
        if any(_matches(address, [block]) for block in removed):
            violations.append(f"diff removes resource block {address}")
    if violations:
        return (
            "Violated",
            list(dict.fromkeys(violations)),
            "a resource the requirement asks to preserve is destroyed or removed",
        )

    if addresses:
        evidence = [
            f"{_digest_ref(summary)}: destroy={summary['destroy']} replace={summary['replace']}; "
            f"destructive actions {destructive_addresses or 'none'} do not include "
            f"{', '.join(addresses)}"
        ]
        return "Satisfied", evidence, ""

    if types:
        type_matches = [
            address
            for address in destructive_addresses + removed
            if any(_matches(address, [tf_type]) for tf_type in types)
        ]
        if type_matches:
            return (
                "Unverified",
                [
                    f"{_digest_ref(summary)}: destructive actions "
                    f"{sorted(set(type_matches))} may match the preserved target"
                ],
                "preserved target identified only by type; cannot attribute the "
                "destructive action to a specific resource",
            )
        evidence = [
            f"{_digest_ref(summary)}: no {', '.join(types)} appears in destructive "
            f"actions {destructive_addresses or 'none'} or diff removals"
        ]
        if destructive or removed:
            return "Satisfied", evidence, ""
        return (
            "Satisfied",
            [
                f"{_digest_ref(summary)}: destroy=0 replace=0",
                "proposed diff removes no resource blocks",
                *evidence,
            ],
            "",
        )

    if not addresses and not types:
        if not destructive and not removed:
            return (
                "Satisfied",
                [
                    f"{_digest_ref(summary)}: destroy=0 replace=0",
                    "proposed diff removes no resource blocks",
                ],
                "",
            )
        return (
            "Unverified",
            [
                f"{_digest_ref(summary)}: destructive actions "
                f"{destructive_addresses or removed}; preserved target not identifiable"
            ],
            "no resource address or type in the requirement text; cannot attribute "
            "the destructive actions",
        )
    return ("Unverified", [], "")


def _evaluate_public_private(
    text: str, diff: str, summary: Mapping[str, Any]
) -> tuple[str, list[str], str]:
    contrary: list[str] = []
    for pattern, label in (
        (_ADDED_PUBLIC_ACL_RE, "diff adds a public ACL"),
        (_ADDED_PAB_FALSE_RE, "diff disables a public access block setting"),
        (_REMOVED_PAB_TRUE_RE, "diff removes a public access block guard"),
    ):
        for match in pattern.finditer(diff):
            contrary.append(f"{label}: {match.group(0).strip()}")

    if contrary:
        evidence = [*_dedupe(contrary), f"{_digest_ref(summary)}"]
        return "Violated", evidence, "proposed changes weaken public-access posture"

    supporting: list[str] = []
    for pattern, label in (
        (_ADDED_PAB_TRUE_RE, "diff sets a public access block guard to true"),
        (_ADDED_PRIVATE_ACL_RE, 'diff adds acl = "private"'),
        (_ADDED_PAB_RESOURCE_RE, "diff adds an aws_s3_bucket_public_access_block resource"),
    ):
        for match in pattern.finditer(diff):
            supporting.append(f"{label}: {match.group(0).strip()}")

    if supporting:
        return (
            "Unverified",
            [*_dedupe(supporting), f"{_digest_ref(summary)}"],
            "observed configuration text in the proposed diff, but source or plan "
            "text alone does not prove the resulting infrastructure is private; "
            "re-run scanners and plan evidence before claiming satisfaction",
        )
    return (
        "Unverified",
        [f"{_digest_ref(summary)}"],
        "no deterministic diff or plan evidence for the access-posture requirement",
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
