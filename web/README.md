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

`lib/client.ts` picks the API implementation at first use (first match wins):

- `NEXT_PUBLIC_API_BASE_URL` set → `HttpApiClient` against the orchestration API.
- else `NEXT_PUBLIC_WORKER_URL` set → `DirectServiceClient` (live worker B + AI C through
  the same-origin `/service/*` proxy; see “Live mode” below).
- else → `MockApiClient` (fixtures in `lib/fixtures.ts`).

The header chip shows `Live API (orchestration)`, `Live worker (direct)` or `Mock services`
so demo state is never ambiguous.

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
- No UI path exists for applying infrastructure changes (the apply command is out of scope).

## Integration requirements

1. B: `POST /tasks/{id}/check` must return `CheckRun[]` where a missing binary or
   crash is `UnableToVerify`, never `Passed`.
2. C: `POST /tasks/{id}/patch` returns a `Patch` with `unified_diff` and `base_digest`.
3. D: `finding` normalization + `plan_summary` feed the workspace; confirm the
   proposed `GET /tasks/{id}` read model and `baseline_findings` field.
4. E: review the provisional shapes above and the fixture/schema tests before merge.

---

## Live mode (services B and C)

Runs the frontend against real HTTP services instead of fixtures. Integration details,
compatibility matrix and evidence: `agents/agent-a-frontend/INTEGRATION_STATUS.md` and
`agents/agent-a-frontend/INTEGRATION_TEST_RESULTS.md`.

### Prerequisites

- Node 20+ / npm (this repo: node v26.8.1, npm 11.19.0), Next 16.4.2.
- Python 3.12 + `uv` (or any Python 3.11+ env able to install FastAPI/uvicorn) for B and C.
- Read access to branches `agent/b-worker` and `agent/c-ai` (for `git archive`).
- Terraform is **not** required: without it every check correctly returns
  `UnableToVerify` (`required executable not found: terraform`). Install it only if you
  want checks to be able to pass.
- No secrets are required anywhere in this flow. Only URLs, ports and paths are configured.

### How the frontend proxy is configured

B and C send **no CORS headers**, so the browser must never call `:8081`/`:8082` directly.
`web/next.config.ts` rewrites same-origin paths to the services:

| Frontend path | Rewrites to | Target env (server side) |
|---|---|---|
| `/service/worker/:path*` | `$WORKER/:path*` | `PLANPROOF_WORKER_URL` ?? `NEXT_PUBLIC_WORKER_URL` |
| `/service/ai/:path*` | `$AI/:path*` | `PLANPROOF_AI_URL` ?? `NEXT_PUBLIC_AI_URL` |

The client stores only the literal `"/service/worker"` / `"/service/ai"` paths
(`lib/client.ts`); setting `NEXT_PUBLIC_WORKER_URL` both **enables** live direct mode and
provides the proxy target. `PLANPROOF_WORKER_URL`/`PLANPROOF_AI_URL` override the target
without changing the inlined public values (useful on servers).

### Start B (worker)

```bash
LIVE=/var/folders/yl/…/T/opencode/pp-live     # any writable dir
mkdir -p "$LIVE" && cd <repo-root>
git archive agent/b-worker worker    | tar -x -C "$LIVE"
git archive agent/b-worker contracts | tar -x -C "$LIVE"   # contracts/ at repo root: required
cd "$LIVE"
uv venv .venv-b --python 3.12
uv pip install --python .venv-b/bin/python -r worker/requirements.txt
cd worker
WORKER_DATA_DIR="$LIVE/worker/workspace-data" \
  "$LIVE/.venv-b/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```

`contracts/` must sit at the parent of the worker package or `/check` 500s
(`FileNotFoundError`). Verify: `curl http://127.0.0.1:8081/health`.

### Start C (ai)

```bash
cd "$LIVE"
git archive agent/c-ai ai | tar -x -C "$LIVE"
uv venv .venv-c --python 3.12
uv pip install --python .venv-c/bin/python -r ai/requirements.txt
cd ai
MODEL_BACKEND=mock "$LIVE/.venv-c/bin/python" -m uvicorn planproof_ai.app:app \
  --host 127.0.0.1 --port 8082
```

Verify: `curl http://127.0.0.1:8082/health` → `{"status":"ok","model_backend":"mock",…}`.

### Start the frontend in live mode

```bash
cd web
npm install
NEXT_PUBLIC_WORKER_URL=http://127.0.0.1:8081 \
NEXT_PUBLIC_AI_URL=http://127.0.0.1:8082 \
  npm run dev          # http://localhost:3000  (use localhost, not 127.0.0.1 — see troubleshooting)
```

### Environment variables (live mode)

| Variable | Required | Purpose | Secret? |
|---|---|---|---|
| `NEXT_PUBLIC_WORKER_URL` | yes (direct mode) | enables `worker-direct` client + proxy target for B | no — URL only |
| `NEXT_PUBLIC_AI_URL` | recommended | proxy target for C (enables requirements/capture-adjacent AI calls) | no — URL only |
| `NEXT_PUBLIC_API_BASE_URL` | no | switches to orchestration mode instead (not implemented yet) | no — URL only |
| `PLANPROOF_WORKER_URL` / `PLANPROOF_AI_URL` | no | server-side proxy target override | no — URL only |

No API keys, tokens or credentials are used or stored by the frontend.

### Run the smoke tests

```bash
python3 agents/agent-a-frontend/smoke_live.py --frontend http://localhost:3000
# → "22/22 checks passed. Screenshots: /tmp/planproof-live-shots"
```

Self-contained: generates its own fixture ZIP, creates a real task on B, runs the full
mandatory check set, attempts capture, exercises the AI failure path, and exits non-zero
on any failed assertion. Requires Playwright for Python + Chromium.

### Distinguishing live inference from mock inference

- **Frontend data source:** header chip must read **`Live worker (direct)`**.
  `Mock services` means fixtures (`lib/fixtures.ts`), not live.
- **Proxy reachability:** `curl http://localhost:3000/service/worker/health` and
  `…/service/ai/health` return **B's and C's** JSON (fields `service`, `model_backend`,
  `model_id`). If they fail, no live traffic is possible.
- **AI service backend:** `model_backend: "mock"` in C's health means C is using its
  **internal mock model adapter** — it is still a real HTTP service (real fail-closed
  error handling is exercised), but **no real model runs**. Real Gemma/SageMaker/Ollama
  inference has **not** been configured or verified; do not claim it from these runs.

### Known limitations and troubleshooting

| Symptom / limit | Explanation |
|---|---|
| Findings / patch / approve / report show “unavailable” | B/C/D do not expose those endpoints yet (orchestration gaps, see `INTEGRATION_STATUS.md` §5). Explicit by design — never silently mocked. |
| Requirements extraction returns `502 … MockLLMAdapter has no preset responses left` | C-side gap: its mock adapter is constructed with no presets. Frontend surfaces the error and fabricates nothing. |
| All checks `UnableToVerify` | Expected without terraform installed. `GET /capabilities` reports `terraform: available=false`. |
| Browser fetch to `:8081`/`:8082` blocked | B/C send no CORS headers — always go through `/service/*` on the frontend origin (never point the browser at raw service URLs). |
| Page loads but React doesn’t hydrate on `http://127.0.0.1:3000` | `next dev` HMR quirk — use `http://localhost:3000`. Prod build is unaffected. |
| Worker `/check` 500 `FileNotFoundError` | `contracts/` missing at the worker’s repo root — extract it (see “Start B”). |
| Refresh loses workspace data | No `GET /tasks/{id}` yet; the workspace is cached in `sessionStorage` per tab and fails closed elsewhere (DEC-07). |
