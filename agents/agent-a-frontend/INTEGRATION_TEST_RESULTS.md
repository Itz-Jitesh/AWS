# PlanProof — Integration Test Results (Agent A, frontend)

Branch `agent/a-frontend` · executed 2026-10-23 · worktree `/Users/jitesh/Coding/workspace/Projects/AWS/planproof-a`
Backend provenance: see `INTEGRATION_STATUS.md` §0 (B @ `7bfbe6c`, C @ `7a5eec8`).

## 1. Unit / integration tests (Vitest)

Command:

```bash
cd web && npm test
```

Final result:

```
 Test Files  13 passed (13)
      Tests  83 passed (83)
```

File inventory: `approval.test.tsx`, `contracts.test.ts`, `diff-viewer.test.tsx`, `direct-client.test.ts`,
`findings.test.tsx`, `mock-client.test.ts`, `plan-summary.test.tsx`, `requirements.test.tsx`,
`service-notice.test.tsx`, `status.test.tsx`, `task-creation-form.test.tsx`, `task-workspace-direct.test.tsx`,
`task-workspace.test.tsx`.

History within Phase 2 (both real, unmodified assertions):

- **80/80** — full suite green after Phase-2 integration work (proxy, direct client, service notices,
  state enum, ADV-06 token removal).
- **83/83** — after adding three *additional fail-closed* approval tests required by deliverable item 4
  (malformed digest, wrong state, `approval_valid=false`). No existing test was weakened, skipped, or
  deleted; test count only increased.

No tests are skipped, `.only`'d, or filtered (`grep` for `.skip|\.only` in `web/tests`: 0 matches).

## 2. Lint, TypeScript, production build

| Check | Command | Result |
|---|---|---|
| ESLint | `cd web && npm run lint` | **Clean** — no errors, no warnings (exit 0, no output) |
| TypeScript | `cd web && npx tsc --noEmit` | **Clean** (exit 0, no output) |
| Production build | `cd web && NEXT_PUBLIC_WORKER_URL=http://127.0.0.1:8081 NEXT_PUBLIC_AI_URL=http://127.0.0.1:8082 npm run build` | **Success** — Next 16.4.2 emits all routes incl. `/`, `/tasks/[id]`, static + PPR markers (exit 0) |
| ADV-06 token scan | `grep -ri "terraform apply" web/components web/tests web/lib web/app web/README.md web/next.config.ts agents/agent-a-frontend/smoke_live.py` | **0 matches** (code scope: UI, lib, tests, README, config, smoke script). The token is quoted only inside these report paragraphs and pre-exists in other agents' `START_PROMPT.md`, outside A's diff |

## 3. Live end-to-end smoke test

Command (exact reproduction):

```bash
# 1. services must be running (see §4), then:
cd web && NEXT_PUBLIC_WORKER_URL=http://127.0.0.1:8081 NEXT_PUBLIC_AI_URL=http://127.0.0.1:8082 npm run dev
# 2. open http://localhost:3000 (localhost — see troubleshooting), then:
python3 agents/agent-a-frontend/smoke_live.py --frontend http://localhost:3000
```

Result: **22/22 passed** (exit 0). Full output:

```
PASS backend chip reports live worker (direct)
PASS task form hydrated (react-controlled radios respond)
PASS task id is worker's 32-hex format
PASS ingest summary shows detected .tf file and aws provider
PASS service notice: Findings (unavailable)
PASS service notice: Patch generation (unavailable)
PASS service notice: Approval (unavailable)
PASS service notice: Evidence report export (unavailable)
PASS generate patch disabled
PASS approve disabled before any plan
PASS report download hidden (endpoint missing)
PASS report-unavailable explanation shown
PASS state marked client-derived (DEC-04 note)
PASS all five checks rendered
PASS every check reports UnableToVerify (no false pass)
PASS unverified banner shown (never 'passed')
PASS client-derived state is CHECKING
PASS capture-unavailable reason surfaced from worker
PASS approve still disabled after capture attempt
PASS ai failure surfaced honestly (no invented requirements)
PASS no requirements fabricated after failure
PASS no uncaught page errors

22/22 checks passed. Screenshots: /tmp/planproof-live-shots
```

Playwright (Python), Chromium; screenshots in `/tmp/planproof-live-shots/`. The smoke creates a real task
against worker B with a generated fixture ZIP (S3 bucket + public-access-block `main.tf`).

## 4. Services started (ports, configuration, backend mode)

| Service | PID / port | Runtime & command (from `ps`) | Working dir | Configuration (no secrets) |
|---|---|---|---|---|
| Worker B | 53101 · `127.0.0.1:8081` | `.venv-b/bin/python` (3.12.11) `-m uvicorn app.main:app --host 127.0.0.1 --port 8081` | `…/pp-live/worker` | `WORKER_DATA_DIR=…/pp-live/worker/workspace-data`; `contracts/` present at `…/pp-live/` |
| AI C | 53200 · `127.0.0.1:8082` | `.venv-c/bin/python` (3.12.11) `-m uvicorn planproof_ai.app:app --host 127.0.0.1 --port 8082` | `…/pp-live/ai` | `MODEL_BACKEND=mock` (`model_id=mock-llm-v1`); **no model-endpoint env configured** |
| Frontend (dev) | 57206 · `:3000` | `next dev` (Next 16.4.2) | `web/` | `NEXT_PUBLIC_WORKER_URL=http://127.0.0.1:8081`, `NEXT_PUBLIC_AI_URL=http://127.0.0.1:8082` |
| Frontend (prod build) | 56431 · `:3001` | `next start` (Next 16.4.2) | `web/` | same env |

Venvs + sources under `/var/folders/yl/1084rmxj735dmt77yh51dfqm0000gn/T/opencode/pp-live/`
(`worker/`, `ai/`, `contracts/`, `.venv-b/`, `.venv-c/`).

**Frontend backend mode for all live runs: `worker-direct`** (`NEXT_PUBLIC_API_BASE_URL` unset →
orchestration client not selected; `NEXT_PUBLIC_WORKER_URL` set → direct client, fetches only the
same-origin `/service/*` proxy paths; mock client not constructed).

## 5. Real services, not mocked service responses

Confirmed — the smoke/browser run did **not** use the frontend mock client and did **not** stub B or C:

1. Backend chip in the running app reports **"Live worker (direct)"** (smoke check 1) — chip text is derived
   from which client class was constructed (`client.ts`), i.e. `DirectServiceClient`, not `MockApiClient`.
2. The browser only ever issues requests to same-origin `http://localhost:3000/service/worker/*` and
   `/service/ai/*`; `next.config.ts` rewrites forward them **server-side** to `127.0.0.1:8081/8082`.
   (B/C send no CORS headers, so a browser could not call them directly at all — §7.)
3. Direct evidence the proxied endpoints answer with live service data:

   ```text
   $ curl http://localhost:3000/service/worker/health
   {"status":"ok","service":"worker","version":"0.1.0"}
   $ curl http://localhost:3000/service/ai/health
   {"status":"ok","model_backend":"mock","model_id":"mock-llm-v1"}
   $ curl -X POST http://127.0.0.1:8081/ingest/upload -F file=@fixture.zip
   → 200 with 32-hex task_id, tf_files, aws provider (session capture)
   $ curl -X POST http://127.0.0.1:8081/check -d '{"task_id":"<32-hex>","checks":["fmt","init","validate","plan","show_json"]}'
   → 5 CheckRuns, all "UnableToVerify" ("required executable not found: terraform")
   $ curl -X POST http://127.0.0.1:8082/tasks/<32-hex>/requirements -d '{"goal":"…"}'
   → 502 {"detail":{"code":"llm_response_invalid","message":"MockLLMAdapter has no preset responses left"}}
   ```

4. Task ids displayed in the UI are worker-minted 32-hex values (smoke check 3); check rows, ingest summary,
   and capture reasons all originate from B's responses (checks 4, 14–19).
5. Smoke has **zero stubbing**: it uses Playwright against the real dev server; all failures of B/C are
   asserted to surface honestly (checks 20–21 prove a live C error, not mock data).

**What "mock" means here:** `MODEL_BACKEND=mock` is C's *internal model adapter*. It is **not** frontend mock
behavior, and **real Gemma/SageMaker/Ollama inference was NOT exercised or verified.**

## 6. Tests skipped, blocked, or not run (disclosure)

| Item | Status | Note |
|---|---|---|
| Phase-1 Playwright visual suite (23/23, ran in Phase 1 against mock-only UI) | **Not re-run in Phase 2** | Component coverage is via the 83 Vitest tests + 22-check live smoke; the Phase-1 script was a throwaway in `/tmp` and targeted the provisional API surface |
| `POST /ingest` with `git_url` against live B | **Not run (live)** | Unit-stub covered; avoided network git clones |
| Large (~MB) ZIP upload through the proxy | **Not run** | Smoke fixture is ~KB; worker advertises a 50 MB upload limit — proxy throughput untested at size |
| 4xx/5xx/timeout client mappings | **Unit-stub only** | Live services did not produce these during smoke (except C's 502, live-verified) |
| `next start` production server E2E | **Not run** | Production build verified (§2); dev server used for smoke |
| Real model inference (Gemma/Ollama/SageMaker) | **Not run** | C runs `MODEL_BACKEND=mock`; no model endpoint configured — no claims made |
| Orchestration mode (`HttpApiClient`) live E2E | **UNVERIFIED** | No orchestration service exists yet (typechecks + factory precedence test only) |

No test was labeled passing without execution.

## 7. Known limitation — AI service C mock-LLM presets (fail-closed on the frontend)

- **Symptom (live, reproducible):** every `POST /tasks/{id}/requirements` returns
  `502 {"detail":{"code":"llm_response_invalid","message":"MockLLMAdapter has no preset responses left"}}`.
- **Cause (C-side):** adapter factory builds `MockLLMAdapter` without preset responses. Requirements
  extraction is therefore non-functional end-to-end regardless of frontend behavior.
- **Frontend behavior (verified):** structured error code+message shown to the user
  (`ai failure surfaced honestly`), requirement list stays empty, **nothing is fabricated**
  (`no requirements fabricated after failure`). The "Extract requirements" button remains available and
  fails honestly again if pressed.
- **Status:** BLOCKED on Agent C (see `INTEGRATION_STATUS.md` §4).

## 8. Known limitation — B/C CORS absent; same-origin proxy mitigation

- `grep` over B's and C's `app/` sources: no `CORSMiddleware`, no `Access-Control-Allow-*` anywhere.
  Direct browser calls to `:8081/:8082` would be blocked by the browser.
- **Mitigation (implemented):** Next rewrites in `web/next.config.ts` expose `/service/worker/:path*` and
  `/service/ai/:path*` as same-origin routes; the client only ever stores `"/service/…"` literal paths
  (`client.ts`). Verified: both health endpoints answer through `localhost:3000`; the proxy adds no CORS
  headers (none needed); the full smoke browser run passes through it.
- Residual risk: none for local single-origin deployments; a first-party/production deployment should decide
  with E/B whether B/C add CORS or stay proxy-only (DEC-INT-01).

## 9. Remaining gaps and risks

1. **Orchestration endpoints absent** — `POST /tasks`, `GET /tasks/{id}`, `/approve`, `/report`, findings
   read route (A-2). Workspace state is session-cached and client-derived; approval/report blocked at the
   client. Owner B (DEC-03/05/06/07) · frontend shows explicit unavailability everywhere (smoke checks 5–12).
2. **C requirements unusable** (§7) · **C patch route unreachable** without server-side workspace resolution
   (DEC-INT-04/05) · **no real model inference verified** (§5).
3. **D has no HTTP surface** — findings panel shows unavailable notice; `baseline_findings` rendering is
   unit-tested but never fed by a live service.
4. **Session-cache-only workspace**: refresh/multi-device flows depend on future `GET /tasks/{id}`; reads
   without cache fail closed with an explanation (unit-tested).
5. **Client-derived state** can lag a future server state machine; chip discloses provenance until DEC-04's
   server state lands. Approval is nonetheless gated on `state === "AWAITING_APPROVAL"` (A-4), so a wrong
   client state cannot authorize anything.
6. **Dev-server quirk:** `next dev` hydrates correctly on `http://localhost:3000` but not
   `http://127.0.0.1:3000` (HMR websocket fails; `__next_f` cleared). Smoke and manual checks must use
   `localhost`. Prod build unaffected (manual probe passed on `127.0.0.1:3001`).
7. **Worker packaging:** B's `/check` requires `contracts/` at the repo root or 500s
   (`FileNotFoundError`) — deployment packaging must include it.
8. **No terraform in environment** → all checks correctly return `UnableToVerify` with limitation
   *"required executable not found: terraform"* (expected fail-closed behavior; recorded, not a defect).
