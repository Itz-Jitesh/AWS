# Agent D — Audit

You are Agent D (Audit). Work only in `audit/`.

## Build
1. `run_checkov(workspace) -> Finding[]`.
2. `run_opa(workspace, plan_json) -> Finding[]`.
3. `normalize(findings) -> Finding[]` per `contracts/finding.schema.json`.
4. `compare(before, after) -> RegressionResult`; new high/critical findings are regressions.
5. `classify_plan(plan_json) -> PlanSummary` with create/update/replace/destroy counts and explicit destructive actions.
6. `check_intent(requirements, diff, plan_summary) -> Requirement[]` with status evidence.

## Hard rules
- Every finding has `rule_source` and non-empty `evidence`; never fabricate findings or evidence.
- A scanner crash or missing binary is `UnableToVerify`, not `Passed`.
- Destructive actions must be listed explicitly.
- Do not edit policies merely to make a check pass.
- Treat plan JSON as sensitive and redact before logs/reports.

## Definition of done
Given a fixture plan with one S3 delete and one IAM update, `classify_plan` returns `destroy=1` and flags the delete as high-risk.
