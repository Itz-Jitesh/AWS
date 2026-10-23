# PlanProof Multi-Agent Build Protocol

## Roles

| Agent | Directory | Owns | Primary output |
|---|---|---|---|
| A — Frontend | `web/` | Next.js UI, task workspace, diff viewer, approval gate, plan badges | Demo screen |
| B — Worker | `worker/` | Repo ingestion, sandboxed Terraform execution, artifact capture | Reliable CheckRuns |
| C — AI | `ai/` | LLM adapter, requirements extraction, patch generation, bounded repair loop | Minimal patches |
| D — Audit | `audit/` | Checkov/OPA adapters, finding normalization, regression comparison, intent check, plan JSON classification | Trustworthy findings and plan summary |
| E — Reviewer | `agents/agent-e-reviewer/` | Contract enforcement, state-machine correctness, adversarial tests, PR review | Rejections or merge approvals |

## Parallelism rule

Each builder works in a separate Git worktree and branch. Do not share a working directory or switch branches inside another agent's worktree.

```bash
git worktree add -b agent/a-frontend ../planproof-a
git worktree add -b agent/b-worker   ../planproof-b
git worktree add -b agent/c-ai       ../planproof-c
git worktree add -b agent/d-audit    ../planproof-d
```

Create the worktrees from the repository root after the initial commit. Agent E reviews PRs from the main repository and does not need a production-code worktree.

## Non-collision contract

Agents communicate through frozen schemas in `contracts/` and typed API boundaries. No agent imports another agent's internal modules.

- A calls B/C/D via HTTP endpoints or mock clients.
- C calls B through a `run_check_suite(workspace, task_id)` interface.
- D is a pure-function-oriented library: `(workspace, plan_json) -> Finding[]`, `(before, after) -> RegressionResult`.
- E reviews diffs and tests; E does not implement production features.

## Merge protocol

1. Agent pushes its branch and opens a PR.
2. E runs contract tests and adversarial fixtures.
3. E merges only if shared schemas are unchanged or version-bumped with a migration note.
4. If a schema must change, E coordinates with affected agents before merge.

## Definition of working in parallel

Two agents are parallel-safe only if neither blocks the other's test suite. If C needs B's Terraform runner, C starts against a mock interface, then switches to the real implementation once B lands the agreed contract.

## State machine

```text
CREATED -> CONTEXT_GATHERING -> REQUIREMENTS_READY -> PROPOSED
-> CHECKING -> (REPAIRING -> CHECKING)* -> REVIEW_READY
-> AWAITING_APPROVAL -> APPLYING -> POST_DEPLOY_CHECKS -> COMPLETE
```

Forbidden transitions:

- `PROPOSED -> APPLYING`
- `CHECKING -> REVIEW_READY` if any mandatory check is `Failed` or `UnableToVerify`
- `AWAITING_APPROVAL -> APPLYING` if the plan digest changed after approval

For the MVP, live apply is out of scope. Keep `APPLYING` unreachable unless the optional apply feature is deliberately implemented, reviewed, and guarded by explicit approval.
