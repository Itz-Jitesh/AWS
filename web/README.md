# PlanProof frontend (`web/`)

Agent A ownership. Next.js App Router + React + TypeScript + Tailwind CSS 4.
No Terraform execution, no Python imports, no live apply.

## Run

```bash
npm install
npm run dev      # http://localhost:3000
npm run lint
npm test
npm run build
```

## Screens

| Route | Purpose |
|---|---|
| `/` | Task creation: ZIP upload or Git URL, goal, Audit/Build mode |
| `/tasks/{id}` | Workspace: checks, requirements, findings, diff, plan summary, approval, evidence report |
| `/tasks/demo` | Fully populated mock workspace with a destructive plan action |

## Data source

`lib/client.ts` picks the API implementation at first use:

- `NEXT_PUBLIC_API_BASE_URL` unset → `MockApiClient` (fixtures in `lib/fixtures.ts`).
- `NEXT_PUBLIC_API_BASE_URL` set → `HttpApiClient` against the orchestration API.

The header chip shows `Mock services` or `Live API` so demo state is never ambiguous.

## Directory map

```
app/            routes (client components only)
components/     reusable typed UI components
lib/            contract types, API client, fixtures, report helpers, tone maps
tests/          vitest + testing-library
test/setup.ts   vitest setup (jest-dom matchers, cleanup)
```

## Contract mapping

`lib/contracts.ts` mirrors `contracts/*.schema.json` field for field
(`schema_version: "1.0.0"`, `additionalProperties: false`). `tests/contracts.test.ts`
validates every fixture against the frozen schemas with Ajv 2020. No contract field
was added, renamed or removed by this package.

## Provisional API surface

Request/response bodies around the TRD §4 endpoints are not frozen yet. This package
uses the following shapes and requires sign-off from Agents B, C and D:

| Endpoint | Request | Response |
|---|---|---|
| `POST /tasks` | `{ repo_source: {kind:"zip",filename} \| {kind:"git_url",url}, goal, mode }` | `{ task_id, state, goal, mode, created_at }` |
| `GET /tasks/{id}` | — | `TaskWorkspace` (below) |
| `POST /tasks/{id}/check` | — | `{ checks: CheckRun[], findings: Finding[] }` |
| `POST /tasks/{id}/patch` | — | `{ patch: Patch }` |
| `POST /tasks/{id}/approve` | `{ plan_digest }` | `{ task_id, approved_plan_digest, approved_at }` |
| `GET /tasks/{id}/report` | — | `EvidenceReport` (below) |

`GET /tasks/{id}` and `baseline_findings` are **proposed additions** (the UI needs one
aggregated read model plus before/after findings for regression display). Agent E must
approve these before they are treated as shared contract.

```ts
interface TaskWorkspace {
  task: TaskRecord;
  requirements: Requirement[];
  checks: CheckRun[];
  findings: Finding[];
  baseline_findings: Finding[];   // proposed
  patch: Patch | null;
  plan_summary: PlanSummary | null;
  approval: { approved_plan_digest: string; approved_at: string } | null;
}

interface EvidenceReport {
  task_id: string;
  generated_at: string;
  tool_versions: Record<string, string | null>;
  checks: CheckRun[];
  findings: Finding[];
  requirements: Requirement[];
  plan_summary: PlanSummary | null;
  limitations: string[];
}
```

Approval always posts the exact digest shown to the user; a digest mismatch must be
rejected by the service.

## Invariants enforced in the UI

- Status labels are limited to `Passed`, `Failed`, `Skipped`, `NotConfigured`,
  `UnableToVerify`, plus task state labels; `UnableToVerify`/`NotConfigured` render as
  warnings and are never displayed as passes.
- The word "Secure" is never used as a verdict.
- Approve is disabled when `plan_summary` is missing, while approving, and after
  approval is recorded; approval is bound to the displayed 64-char digest.
- Destructive plan actions get a red banner, a red Destroy tile and per-action risk
  chips.
- The evidence report exports limitations and tool versions and states that it is not
  a security guarantee.
- No UI path exists for `terraform apply`.

## Integration requirements

1. B: `POST /tasks/{id}/check` must return `CheckRun[]` where a missing binary or
   crash is `UnableToVerify`, never `Passed`.
2. C: `POST /tasks/{id}/patch` returns a `Patch` with `unified_diff` and `base_digest`.
3. D: `finding` normalization + `plan_summary` feed the workspace; confirm the
   proposed `GET /tasks/{id}` read model and `baseline_findings` field.
4. E: review the provisional shapes above and the fixture/schema tests before merge.
