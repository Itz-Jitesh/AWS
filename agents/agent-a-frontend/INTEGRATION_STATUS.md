# PlanProof — Integration Status Report (Agent A, frontend)

Branch: `agent/a-frontend` · Scope: `web/` + `agents/agent-a-frontend/`
Report status: Phase 2. Answers below are written against the authoritative question text in
`agents/agent-e-reviewer/INTERFACE_CONFIRMATIONS.md` retrieved from branch `agent/e-reviewer` @ `af13e81eb0d86f83c08b47cb9efe8f77a89a4afd`.

## 0. Backend provenance used for live integration

| Component | Source | Revision | How obtained |
|---|---|---|---|
| Worker service (B) | branch `agent/b-worker` | `7bfbe6c0500bc8fe70d73b86078275ef230f6a66` — *feat(worker): FastAPI execution layer with sandboxed checks and contract-compliant CheckRuns* | `git archive agent/b-worker worker` → `/var/folders/yl/1084rmxj735dmt77yh51dfqm0000gn/T/opencode/pp-live/worker` |
| AI service (C) | branch `agent/c-ai` | `7a5eec843a8052625f9ccb2a08a47ae751e7d285` — *feat(ai): LLM adapters, requirements extraction, safe patch engine, bounded repair loop* | `git archive agent/c-ai ai` → `.../pp-live/ai` |
| Runtime contracts | branch `agent/b-worker` (B's copy of `contracts/`) | same commit `7bfbe6c` | `git archive agent/b-worker contracts` → `.../pp-live/contracts` |
| Reviewer interface docs | branch `agent/e-reviewer` | `af13e81` | `git show agent/e-reviewer:agents/agent-e-reviewer/INTERFACE_CONFIRMATIONS.md` |

**Limitation disclosed:** E states all branch copies of `contracts/` are byte-identical to the original
scaffold contract (`52649fa`). A used B's copy for the live worker and did not independently re-hash it
against the scaffold commit. The frontend itself never reads `contracts/` files at runtime; it validates
against the TypeScript mirrors in `web/lib/contracts.ts` + `web/lib/validate.ts`.

---

## 1. Answers to E's questions A-1 … A-5

Questions quoted verbatim from `INTERFACE_CONFIRMATIONS.md` (§ *Request to Agent A — frontend (DEC-04, DEC-06, DEC-07)*).

### A-1

> Confirm the 11-state enum covers every screen state, and that `AwaitingApproval` remains a **UI label
> mapped from `AWAITING_APPROVAL`**, never a contract `status` value (CE-04). Which frontend field carries it?

**Answer: CONFIRMED.**

- **11-state enum covers every screen state:** yes. `web/lib/contracts.ts` `TaskState` is exactly
  `CREATED | CONTEXT_GATHERING | REQUIREMENTS_READY | PROPOSED | CHECKING | REPAIRING | REVIEW_READY | AWAITING_APPROVAL | APPLYING | POST_DEPLOY_CHECKS | COMPLETE` (11). Every state renders through
  `TASK_STATE_LABELS` in `web/lib/ui.ts`, typed `Record<TaskState, string>` — exhaustiveness is enforced by
  `tsc --noEmit` (a new state without a label fails the build). Unknown strings fall back to the raw value
  (`ui.ts` line 127: `TASK_STATE_LABELS[state] ?? state`), never to a success-like label.
- **`AwaitingApproval` is only a UI label:** yes — grep for the camel-case token `AwaitingApproval` across
  `web/` returns **zero matches**. The contract value is `"AWAITING_APPROVAL"` (`TaskState`).
  The UI label rendered for it is `"Awaiting approval"` (`ui.ts` line 120), produced by `taskStateLabel()`.
- **Which frontend field carries it:** `TaskRecord.state` (`web/lib/api.ts` line 23), rendered as the state
  chip (`data-testid="task-state"`), and passed to `ApprovalPanel` as its `state` prop where it is compared
  strictly: `state === "AWAITING_APPROVAL"` gates the approve button.

### A-2

> `task-view` currently exposes: state, goal, mode, plan_digest, approval_valid, requirements, repair_attempt,
> active_check_suite. **Is that sufficient to render the workspace, or do you need a findings/checks read route
> (e.g. `GET /tasks/{id}/findings`)?** If needed, say so now — new endpoint, not a field patch.

**Answer: NOT SUFFICIENT. A findings/checks read route is needed, plus plan/ingest fields on a read model.**

Evidence — the proposal at `agents/agent-e-reviewer/proposals/schemas/task-view.schema.json` @ `af13e81`
exposes exactly: `schema_version, task_id, state, created_at, updated_at, goal, mode, plan_digest,
approval_valid, requirements, active_check_suite, repair_attempt` — and `active_check_suite` is typed
`string | null` (a suite **label**, not `CheckRun[]`).

The workspace UI (`web/components/TaskWorkspace.tsx`) additionally renders, from `TaskWorkspace`
(`web/lib/api.ts`):

| UI section | Data required | Present in `task-view`? |
|---|---|---|
| Check suite (5 rows, durations, limitations) | `checks: CheckRun[]` | **No** |
| Findings panel + baseline | `findings`, `baseline_findings` | **No** — **new route needed** (`GET /tasks/{id}/findings` as E offers) |
| Plan summary / destructive actions | `plan_summary` (counts, risk classes) | **No** (only in `task-report`) |
| Patch panel | `patch` | **No** (C `task-patch` route, also blocked — see §7) |
| Plan capture card | `plan_capture` (`available`, `reason`, `plan_digest`) | **No** |
| Ingest summary | `ingest` (tf_files, provider) | **No** |
| Approval record display | `approval` (`approved_plan_digest`, `approved_at`) | **No** (only `approval_valid: boolean`) |
| Evidence report summary | `tool_versions`, `limitations` | **No** (only in `task-report`) |

Requested now, per E's instruction (new endpoint, not a field patch):

1. **`GET /tasks/{id}/findings`** → `findings` + `baseline_findings` (required for FindingsList).
2. **Checks read**: either `task-view` carries `active_check_suite` as `CheckRun[]` (field change to the
   current proposal) or the findings route also returns the current suite's `CheckRun[]`. A needs the full
   rows (status, duration, limitation, check_id), not a label.
3. **Plan/ingest/capture/approval fields** must ride on `task-view` or the findings route —
   `plan_summary`, `plan_capture`, `ingest`, `approval`. Until they exist, A fails closed: client-derived
   state only (chip marked "client-derived", DEC-04), session-storage workspace cache instead of
   `GET /tasks/{id}` (DEC-07), approval blocked unless a classified summary exists (§4).

Until then the workspace is demonstrably renderable in live mode (83/83 tests, 22/22 smoke), but only with
data the worker returns directly (ingest, checks, capture) plus explicit unavailability notices for the rest.

### A-3

> Report fields: do you render `regression_result` and `patch` inline from `/report`, or fetch separately?
> Any field you need that is absent?

**Answer: fetched separately (download only). Neither `regression_result` nor `patch` is rendered from `/report`.**

- `EvidencePanel` (`web/components/EvidencePanel.tsx`): the download button calls
  `onDownload → GET /report` and saves the raw payload via `downloadJson` (blob). No field-level rendering
  of the report payload happens in the UI.
- The **in-page** evidence summary (tool versions, limitations, counts) is built from workspace data by
  `web/lib/report.ts` collectors — it does not depend on `/report`.
- `patch` renders from `workspace.patch` (patch panel), not from `/report`.
- `regression_result` has **no UI today** (post-patch comparison view is future work).
- **Fields needed that are absent from my `EvidenceReport` consumption:** none for download-as-JSON (raw
  passthrough). For the in-page trust display once DEC-06 lands, A wants `redacted` (constant `true`,
  already required by the proposal — currently not surfaced) and would later surface `regression_result`
  and `approval` inline. Nothing else is missing from E's `task-report` proposal.
- Live status: `/report` endpoint does not exist → **BLOCKED (DEC-06)**; the download button is hidden and an
  explicit explanation is shown (smoke checks `report download hidden (endpoint missing)` and
  `report-unavailable explanation shown`).

### A-4

> Approve button rules: disabled unless `plan_digest` is non-null **and** state is `AWAITING_APPROVAL` and
> `approval_valid` is not false. Confirm.

**Answer: CONFIRM — and the rule is enforced as of Phase 2.**

`ApprovalPanel` (`web/components/ApprovalPanel.tsx`) computes:

```
canApprove = planSummary (classified, non-null ⇒ plan_digest non-null)
          AND DIGEST_PATTERN (64-hex) matches
          AND state === "AWAITING_APPROVAL"
          AND approval_valid !== false
          AND approve endpoint available (no unavailableReason)
          AND no approval already recorded
```

Note: A implements E's "plan_digest non-null" **stricter** — digest must be a 64-hex sha256 *and* come with a
classified `plan_summary` (counts + destructive actions) before consent can be recorded
(DEC-INT-03/06 compatible). `TaskRecord` gained `approval_valid?: boolean | null` (optional until
`task-view` lands; the proposal marks it **required**).

Fail-closed verification for "missing, malformed, stale, rejected approval data" — none can authorize:

| Data condition | Behavior | Evidence |
|---|---|---|
| Missing digest / no plan | Approve disabled | `web/tests/approval.test.tsx` *"disables approval when the plan digest is missing"*; `web/tests/mock-client.test.ts` *"rejects approval when there is no plan"*; smoke `approve disabled before any plan` |
| Malformed digest (≠ 64-hex) | Approve disabled | `approval.test.tsx` *"disables approval when the plan digest is malformed"* |
| Wrong state (not `AWAITING_APPROVAL`) | Approve disabled | `approval.test.tsx` *"disables approval when the task state is not awaiting approval"* |
| Server says `approval_valid: false` | Approve disabled | `approval.test.tsx` *"disables approval when the server marks approval_valid as false"* |
| Stale digest (plan changed) | Approval rejected, no consent recorded | `mock-client.test.ts` *"rejects approval when the plan digest differs"* |
| Server/client rejection | Error shown, consent not recorded, button re-enabled | `approval.test.tsx` *"surfaces a rejected approval without recording consent"* |
| Already approved | Approve button removed, recorded digest shown | `approval.test.tsx` *"shows a recorded approval and hides the approve button"* |
| Live mode (endpoint absent) | Approve hard-blocked | smoke `approve disabled before any plan` + `approve still disabled after capture attempt`; `direct-client.test.ts` *"fails closed for blocked operations"* (`not_supported`) |

### A-5

> `mode` enum `audit \| build` matches your mode selector exactly?

**Answer: CONFIRM — exact match.**

- Contract: `type TaskMode = "audit" | "build"` (`web/lib/contracts.ts` line 26), matching E's
  `task-create` proposal.
- Selector: `TaskCreationForm` declares `MODES: Array<{ value: TaskMode; … }>` (line 11–12) and the form state
  is typed `useState<TaskMode>` — a mismatched option is a compile error.
- Test: `web/tests/task-creation-form.test.tsx` *"creates a task with the entered repo source, goal and mode"*
  asserts the submitted payload carries the selected mode.

---

## 2. Compatibility matrix

Legend: **PASS** verified end-to-end or by a named test · **PARTIAL** works with disclosed limits ·
**FAIL** boundary unreachable/non-conforming · **BLOCKED** endpoint or decision missing ·
**UNVERIFIED** not exercised.

### 2.1 Frontend → Worker B (via same-origin proxy)

| Boundary | Schema/contract | Status | Evidence |
|---|---|---|---|
| `GET /health` | `{status, service, version}` | **PASS** | Live: `curl /service/worker/health` → `{"status":"ok","service":"worker","version":"0.1.0"}` (2026-10-23 session); smoke prerequisite |
| `GET /capabilities` | capabilities object | **PASS** | Live curl (records `terraform: available=false` — drives UnableToVerify expectations) |
| `POST /ingest/upload` (multipart `file`) | `{task_id, tf_files, aws_provider…}` | **PASS** | `direct-client.test.ts` *"uploads a zip file as multipart form data"*; live smoke task creation returns 32-hex id + ingest summary rendered (`ingest summary shows detected .tf file and aws provider`) |
| `POST /ingest` (JSON `git_url`) | `{source_type, git_url}` + 32-hex validation | **PARTIAL** | Unit PASS (`direct-client.test.ts` *"ingests a git_url source and caches the workspace"*); **live UNVERIFIED** — no network clone attempted this session |
| `POST /check` (full mandatory set `{fmt,init,validate,plan,show_json}`) | `CheckRun[]` via `isCheckRunList` | **PASS** | `direct-client.test.ts` *"requests the full mandatory check set and derives REVIEW_READY when all pass"*; live smoke: 5 rows rendered, all `Unable to verify` (`required executable not found: terraform` — correct fail-closed result, no terraform present) |
| `POST /capture` | `{available, reason?, plan_digest?}` | **PASS** | `direct-client.test.ts` *"captures the plan digest and rejects malformed digests"* + *"keeps capture-unavailable responses explicit"*; live smoke: worker's capture-unavailable reason surfaced; digest format re-validated client-side |
| Error envelope `{detail:{code,message}}` | typed `ApiError` mapping | **PASS** | `direct-client.test.ts` — 404 `TASK_NOT_FOUND`, 422 `CHECK_NOT_ALLOWED`, structured-5xx surfaced (`code`+`message` only), unstructured 5xx → generic `HTTP nnn` (bodies never echoed), timeout → `ApiError("timeout")` |
| `GET /tasks/{id}` (task-view) | E proposal | **BLOCKED** | No route on B. Fallback: sessionStorage workspace cache (`"requires a cached session for workspace reads"`), documented DEC-07/B-7 |
| `POST /approve` | task-approve | **BLOCKED** | No route on B (DEC-05/B-5). Client: `not_supported` + `ApprovalPanel` unavailable banner |
| `GET /report` | task-report | **BLOCKED** | No route on B (DEC-06/B-6). Download hidden + explanation (smoke) |
| `GET /tasks/{id}/findings` | requested in A-2 | **BLOCKED** | Endpoint does not exist; findings panel shows unavailable notice (smoke `Findings (unavailable)`) |

### 2.2 Frontend → AI service C (via same-origin proxy)

| Boundary | Schema/contract | Status | Evidence |
|---|---|---|---|
| `GET /health` | `{status, model_backend, model_id}` | **PASS** | Live: `{"status":"ok","model_backend":"mock","model_id":"mock-llm-v1"}` direct + via proxy |
| `POST /tasks/{id}/requirements` `{goal}` | `{requirements: Requirement[]}` | **FAIL (service-side)** | Live every call returns `502 {"detail":{"code":"llm_response_invalid","message":"MockLLMAdapter has no preset responses left"}}` (curl 2026-10-23). Contract **shape** verified client-side when a valid body arrives: `direct-client.test.ts` *"extracts requirements from the AI service and validates the contract"*. Frontend handling is PASS (see §2.5): error surfaced verbatim, no requirements fabricated (smoke: `ai failure surfaced honestly (no invented requirements)`, `no requirements fabricated after failure`) |
| `POST /tasks/{id}/patch` | task-patch | **BLOCKED** | Requires server-side workspace path (DEC-INT-04: A must not send one) + orchestration to resolve task→workspace (DEC-INT-05) |
| Real model inference (Gemma/Ollama/SageMaker) | — | **UNVERIFIED** | `MODEL_BACKEND=mock` only; **no real model endpoint was exercised or is claimed** |

### 2.3 Frontend → same-origin `/service/*` proxy

| Boundary | Status | Evidence |
|---|---|---|
| `next.config.ts` rewrites `/service/worker/:path* → $WORKER/:path*`, `/service/ai/:path* → $AI/:path*` | **PASS** | `web/next.config.ts` lines 29–44; targets from `PLANPROOF_* ?? NEXT_PUBLIC_*` env |
| Browser requests are same-origin (`localhost:3000/service/...`), no CORS dependency | **PASS** | Smoke runs entirely through `http://localhost:3000`; `curl /service/worker/health` and `/service/ai/health` return live JSON; proxy health probe returns no `Access-Control-Allow-*` headers (correct — same-origin doesn't need them) |
| Client never targets cross-origin service URLs | **PASS** | `web/lib/client.ts`: `DirectServiceClient` is constructed with literal `"/service/worker"` / `"/service/ai"` paths, never the raw service URL |
| Why the proxy exists (B/C send no CORS headers) | **PASS** | `grep CORSMiddleware\|Access-Control-Allow` over B's and C's `app/` source: **zero matches**; direct cross-origin browser calls are impossible. Mitigation: this proxy (DEC-INT-01 alias) |

### 2.4 Request/response schemas (client-side contract validation)

| Boundary | Status | Evidence |
|---|---|---|
| CheckRun validation (fail-closed: bad/empty suite → error, never pass) | **PASS** | `web/lib/validate.ts`; `direct-client.test.ts` *"fails closed on an empty check suite"* + *"fails closed when a run does not match the check contract"*; `contracts.test.ts` fixtures |
| 32-hex task ids (DEC-INT-09) | **PASS** | Live ids from B match `^[0-9a-f]{32}$` (smoke `task id is worker's 32-hex format`); `validate.ts` |
| Digest 64-hex (ADV-02/DEC-INT-03) | **PASS** | `DIGEST_PATTERN`; capture test rejects malformed digests |
| Requirements/ingest/capture/plan-summary shapes | **PASS** (unit) / live partial | Validators + success-path stubs in `direct-client.test.ts`; live exercised for ingest, check, capture only |
| Error envelope | **PASS** | See §2.1 error row |

### 2.5 State-enum compatibility

| Boundary | Status | Evidence |
|---|---|---|
| 11-state enum adopted, labels + tones for all 11 | **PASS** | `contracts.ts` (added `APPLYING`, `POST_DEPLOY_CHECKS`), `ui.ts` `Record<TaskState,string>` (tsc-enforced) |
| Client-reachable states today | **PARTIAL** | Direct mode derives only `CREATED` / `CHECKING` / `REVIEW_READY` (`deriveState`, marked "client-derived" — DEC-04 note in smoke); mock demo uses `AWAITING_APPROVAL`; remaining states render-only until B's state machine (DEC-03) |
| Unknown state never rendered as success | **PASS** | label fallback is the raw string (`?? state`), tone falls back neutral |

### 2.6 Approval behavior

| Boundary | Status | Evidence |
|---|---|---|
| A-4 rule enforced (digest + classified summary + 64-hex + state + approval_valid) | **PASS** | §1/A-4 table — 8 approval tests |
| No apply path (ADV-06) | **PASS** | `grep -ri "terraform apply" web/components web/tests web/lib web/app web/README.md web/next.config.ts agents/agent-a-frontend/smoke_live.py` → **0 matches**. (The token appears only inside this report's *quoted* verification commands and in other agents' `START_PROMPT.md` — never in A's code, UI, README, or scripts.) |
| Approval without live endpoint impossible | **PASS** | smoke: approve disabled before plan and after capture attempt; `not_supported` in direct mode |

### 2.7 Token handling

| Boundary | Status | Evidence |
|---|---|---|
| No `terraform apply` token in A's deliverables | **PASS** | Code-scope grep above (0 matches in scope); the phrase exists only in this report's quoted scan commands |
| No credentials in code, logs, or test artifacts | **PASS** | Configured env values are URLs + `MODEL_BACKEND=mock` + `WORKER_DATA_DIR` (path) only — captured via `ps eww` on service PIDs; no API keys anywhere in web config/tests; smoke stdout and screenshots (`/tmp/planproof-live-shots`) contain only UI text and public fixture data (S3 bucket name, public-access-block) |

### 2.8 Mock vs live backend behavior

| Boundary | Status | Evidence |
|---|---|---|
| Mode precedence `API_BASE_URL` (orchestration) → `NEXT_PUBLIC_WORKER_URL` (live direct) → mock | **PASS** | `direct-client.test.ts` *"prefers the orchestration API, then the worker, then mock"*; `client.ts` |
| Backend visible to the user | **PASS** | `AppShell` chip: "Live worker (direct)" / "Mock services" / "Live API (orchestration)"; smoke `backend chip reports live worker (direct)` |
| **No mock fallback after live failure** | **PASS** | Client chosen once at construction (`resolveApiClient`); runtime failures propagate as typed `ApiError` (no catch-to-mock path exists in `direct-client.ts`); smoke proves it live: AI 502 → honest error banner, zero fabricated data |
| Live requests actually hit B/C | **PASS** | See `INTEGRATION_TEST_RESULTS.md` §"Real services, not mocks" (proxy curl outputs, service health JSON, worker-generated task ids) |

---

## 3. Decisions taken while blocked (pending E/B sign-off — no frozen contract modified)

1. **Same-origin `/service/*` proxy** (`web/next.config.ts`) — B/C emit no CORS headers (proven in §2.3);
   browser must not call cross-origin services directly. This realizes DEC-INT-01's alias option.
2. **ZIP ingest via multipart `POST /ingest/upload`** — matches B's implemented route and E's B-2
   multipart-vs-JSON question (frontend never builds `zip_base64` payloads; `RepoSource` is `zip | git_url`).
3. **Session-storage workspace cache** instead of `GET /tasks/{id}` (DEC-07 gap) — fail-closed: reads without a
   session error out; state shown as "client-derived".
4. **Client-derived state** limited to `CREATED|CHECKING|REVIEW_READY` with visible provenance note
   (DEC-04 asks how label mapping is surfaced; the state chip says "client-derived").

## 4. Findings for other agents (not frontend defects)

- **→ Agent C:** `create_adapter` constructs `MockLLMAdapter` with **no preset responses**, so every
  `POST /tasks/{id}/requirements` returns `502 llm_response_invalid`. Requirements extraction is untestable
  end-to-end; the frontend surfaces this honestly. Also no real model backend (Ollama/SageMaker/Gemma)
  configured or verified.
- **→ Agent B:** worker emits **no CORS headers** (frontend mitigates via proxy; a future deployment
  decision may want CORS or first-party serving). Worker `/check` requires `contracts/` at the repo root —
  without it the service 500s (`FileNotFoundError`); deployment packaging note. Also the missing
  orchestration endpoints (A-2, DEC-03/05/06/07).
- **→ Agent D:** no HTTP surface exists; findings are BLOCKED in live mode (client shows unavailable notice).

## 5. Remaining blockers (owner · decision ref)

| Blocker | Owner | Ref |
|---|---|---|
| `POST /tasks`, state machine, `GET /tasks/{id}`, findings/checks read route (A-2) | B | DEC-03, DEC-07, B-7 |
| `POST /tasks/{id}/approve`, `GET /tasks/{id}/report` | B | DEC-05/B-5, DEC-06/B-6 |
| Requirements presets + real model backend; patch workspace resolution | C | DEC-INT-04/05, CE-11 |
| Findings exposure (HTTP) | D | DEC-02 |
| Schema freeze + sign-off on A-1..A-5 answers + proxy decision | E | SCHEMA_FREEZE_PACKAGE, DEC-INT-01 |
