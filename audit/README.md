# audit/ — PlanProof deterministic audit and plan analysis (Agent D)

Pure-function library. No network, no cloud calls, no `terraform apply`, no
imports from other agents' directories. All emitted payloads are validated
against the frozen shared schemas in `contracts/` (version **1.0.0**).

## Public API

```python
from audit import (
    normalize, run_checkov, run_opa, compare,
    classify_plan, plan_digest, verify_digest, check_intent,
    operational_finding,
)

run_checkov(workspace, *, executable=None, timeout_sec=120.0) -> list[Finding]
run_opa(workspace, plan_json, *, executable=None, policies_dir=None, timeout_sec=120.0) -> list[Finding]
normalize(findings: Iterable[raw]) -> list[Finding]
compare(before: list[Finding], after: list[Finding]) -> RegressionResult
classify_plan(plan_json: dict) -> PlanSummary
plan_digest(plan_json: dict) -> str                # 64-hex sha256
verify_digest(plan_json: dict, expected: str) -> bool
check_intent(requirements: list[Requirement], diff: str, plan_summary: PlanSummary) -> list[Requirement]
```

`Finding`, `PlanSummary`, and `Requirement` are dicts matching
`contracts/finding.schema.json`, `contracts/plan-summary.schema.json`, and
`contracts/requirement.schema.json`. Invalid inputs raise
`audit.errors.ContractValidationError` / `InvalidPlanError` / `NormalizationError`
(all subclass `AuditError`) — failures are exceptions or explicit
`UnableToVerify` records, never silent success.

## Scanner failure representation (schema 1.0.0 limitation)

The shared Finding schema has no field for "this record is an operational
failure, not a policy result". Convention used until a coordinated version
bump:

* `rule_source`: `"custom"` (never `checkov`/`opa`)
* `rule_id`: reserved namespace `scanner.<tool>.<kind>` where kind is one of
  `binary_missing | workspace_missing | timeout | execution_failed |
  malformed_output | eval_failed | invalid_plan | policy_unavailable |
  no_results | partial_scan`
* `severity`: `"unknown"`, `status`: `"UnableToVerify"` (or `NotConfigured`
  for `no_results`), `evidence`: redacted, factual failure detail

**Proposed extension** (do not apply without team coordination): add
`record_kind: "policy" | "operational"` to finding.schema.json with a schema
version bump + migration note, or a sibling `ScannerFailure` contract.

## RegressionResult (`compare` → `.to_dict()` for transport)

| field | meaning |
|---|---|
| `regressions` | became `Failed` (new or previously not failed), severity `critical`/`high` |
| `new_findings` | every record only in `after` |
| `resolved` | confirmed resolved: explicit `Passed` counterpart, or absent while `after_scan_complete` |
| `unconfirmed_resolved` | **not resolutions** — prior failures with no confirming evidence (scanner gap / empty after) |
| `missing_after` | previously non-failing records that disappeared; disappearance ≠ pass |
| `unchanged` | same fingerprint and status (persistent gaps live in `evidence_gaps`) |
| `status_changes` | same fingerprint, different status (list may overlap `regressions`) |
| `evidence_gaps` | all `UnableToVerify`/`NotConfigured` records from either side |
| `has_regressions` | `regressions` non-empty |
| `resolved_confirmed` | false when `unconfirmed_resolved` is non-empty |
| `after_scan_complete` | after non-empty and gap-free |
| `notes` | human-readable decision trail |

**Consumers (A, C) must treat `resolved_confirmed == false`, any
`unconfirmed_resolved` entry, and any `evidence_gaps` entry as "not fixed".

## Plan digest

SHA-256 over canonical JSON of the whole plan document:
`json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`.
Key order/whitespace independent; any attribute change invalidates it.
`verify_digest` fails closed on malformed digests. Never log plan values —
only the digest.

## `classify_plan` semantics

* `["delete","create"]` (any order) → **replace**, always `risk: "high"`,
  reason states destroy-and-recreate — never counted as update.
* `["delete"]` → destroy, `risk: "high"`; every destructive action is listed
  with a reason (plus terraform `action_reason` when present).
* `mode: "data"` resources and `read`/`no-op` are ignored.
* Structural garbage (unknown actions, missing addresses, non-object plan)
  raises `InvalidPlanError` — never a silently empty summary.

## `check_intent` semantics

Rules (worst status wins): preservation, access posture, no-changes;
anything else → `Unverified`.

* `Violated` requires proven destruction/removal (named address) or proven
  weakening (diff text).
* `Satisfied` always carries plan/diff evidence; access-posture requirements
  are **never** `Satisfied` from config text alone (source text does not
  prove deployed state — see integration notes).

## Rego policies (`policies/`, `import rego.v1`, OPA ≥ 0.59)

`s3_public.rego` (public ACL / disabled public-access block),
`iam_wildcard.rego` (Allow on `Resource "*"`),
`plan_destroy.rego` (any planned delete, incl. replacement).
Evaluated as `opa eval --format json -d policies -i input.json
data.planproof.deny.deny` with input `{"plan": <plan json>}`.

## Running tests

```bash
# from the repository worktree root
uv venv .venv && uv pip install --python .venv/bin/python pytest jsonschema
cd audit && ../.venv/bin/python -m pytest
```

152 tests. Fake `checkov`/`opa` executables cover missing binary, timeout,
crash, malformed, empty, and partial-scan paths; `skipif`-gated integration
tests run when `.venv/bin/opa` / `.venv/bin/checkov` exist (both validated:
opa 1.6.0, checkov 3.3.30).

## Notes for Agent A (frontend)

* Transport shapes: Finding/PlanSummary/Requirement per contracts;
  `RegressionResult` via `to_dict()` (fields above — fixture it in `web/`).
* Never render `UnableToVerify`/`NotConfigured` as passing; show
  `resolved_confirmed` / `evidence_gaps` in the evidence report.
* `verify_digest(plan, digest)` is the approval-gate primitive; disable
  Approve when the digest is missing or mismatched.

## Notes for Agent C (AI)

* Call this library (or the HTTP wrapper) for findings/plan/intent — do not
  re-implement classification.
* `check_intent` returns final statuses after each patch attempt; a mandatory
  requirement that is `Unverified` or `Violated` must stop the repair loop
  from claiming success (loop may still continue within the 3-attempt budget).
* Intent evidence is derived from plan/diff only — never from the model's
  rationale, and never send plan values (only redacted diagnostics) to the LLM.
