# PlanProof — Product Requirements Document

## 1. Product

An AI infrastructure engineering harness that audits Terraform, generates minimal patches, verifies them deterministically, repairs failures within bounds, and requires human approval before apply.

## 2. MVP scope

### In scope
1. Upload a Terraform repository as a ZIP or provide a public Git URL.
2. Detect `.tf` files and provider versions.
3. Run `terraform fmt -check` and `terraform validate` in an isolated worker.
4. Run Checkov and a small OPA/Rego policy set.
5. Normalize results into one `Finding` schema.
6. Accept a natural-language goal and store mandatory `Requirement[]`.
7. Generate a minimal unified diff; never rewrite the repository wholesale.
8. Run a bounded repair loop: maximum three attempts, with a full re-check after each patch.
9. Compare findings before and after; flag regressions.
10. Flag requirements that remain `Unverified`.
11. Parse `terraform show -json` and classify create/update/replace/delete actions.
12. Display an evidence report with tool versions, plan digest, and limitations.
13. Require approval tied to the exact plan digest.

### Explicitly out of scope for MVP
- Live cloud deployment (optional stretch only).
- Drift detection against real state.
- Cost estimation.
- Git PR comments.
- CloudFormation/Pulumi support.
- Multi-user auth/teams.

## 3. Users
- Hackathon developer deploying an app without deep AWS experience.
- Platform engineer auditing a repository.
- Security reviewer triaging IaC findings.

## 4. Demo script (3 minutes)
1. Load a demo repo containing a public S3 bucket and a wildcard IAM policy.
2. Audit finds representative critical/high and medium findings.
3. User asks: “Make the bucket private without deleting it.”
4. Agent C proposes a patch that adds an S3 public-access-block resource or equivalent safe configuration.
5. The repair loop re-runs Checkov and OPA; results are shown as evidence, not as a blanket security guarantee.
6. Intent check reports whether the “preserve bucket” requirement is satisfied, unverified, or violated.
7. Plan summary shows expected resource changes and explicitly surfaces any destroy/replace actions.
8. User reviews the exact plan digest and approves the proposed plan for the demo workflow.
9. Evidence report downloads.

## 5. Success criteria
- A task can never reach `APPLYING` without passing through `AWAITING_APPROVAL`.
- A scanner crash is never labeled `Passed`.
- A repair that deletes an unrelated resource is blocked.
- The report contains tool versions and a plan digest.
- Approval becomes invalid if the plan digest changes.

## 6. Competitor sentence

“PlanProof refuses to call a repair fixed until the original intent is re-checked, the full suite is re-run, and a human approves the exact plan hash.”
