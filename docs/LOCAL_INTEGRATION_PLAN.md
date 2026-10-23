# PlanProof — Local-First Consolidation Plan

Status: Phase B (integration plan). Supersedes the AWS deployment mission.
No AWS/SageMaker/cloud inference is used. Target: macOS Apple Silicon, 16 GB
unified memory, local model runtime.

## 1. Discovery snapshot (Phase A)

### Branches and commits (all unmerged, all based on `52649fa`)

| Agent | Branch | Tip | Scope |
|---|---|---|---|
| A | `agent/a-frontend` | `569c8da` | `web/` Next.js UI, direct/live clients, integration docs |
| B | `agent/b-worker` | `0507f71` | `worker/` FastAPI execution + CORS |
| C | `agent/c-ai` | `da8862d` | `ai/` LLM adapters, patch engine, repair loop, `/capabilities` |
| D | `agent/d-audit` | `3678880` | `audit/` deterministic audit library (checkov/opa/plan/intent) |
| E | `agent/e-reviewer` | `af13e81` | audit/review docs only — **not merged** (unfinished by its own gate; BLOCK recommendation stands) |

Worktrees `planproof-a|b|c|d` are clean at those tips. `main` = `52649fa`.
Only untracked file: `Archive.zip` (agent prompt archive, 97 KB; never read/extracted/committed).

### Verified tooling on this machine

- Ollama 0.32.9 running at `127.0.0.1:11434`, **no models pulled yet**.
- `gemma4:e4b` exists in the Ollama registry (6.6–9.5 GB, 128K ctx, multimodal).
- No PlanProof LoRA adapter exists anywhere (no safetensors/GGUF found; the colab
  notebook is a placeholder with `REPLACE_WITH_VERIFIED_MODEL_ID` and `dataset = None`).
- Node 26.8.1 / npm 11.19.0; Python 3.14.6; `uv` present.
- `terraform`, `checkov`, `opa` are **not on PATH**. D's worktree `.venv` already
  contains validated `checkov 3.3.30` and `opa 1.6.0`; `brew` is available.
- Disk: ~98 GB free. E2E Playwright/Chromium already cached.

### Interface mismatches carried over from E's audit (must be fixed here)

1. C→B `/check`: C sends `{workspace, task_id}`, B expects `{task_id, checks}` (422); response key `runs` vs `checks`.
2. C→B `/capture`: C sends `{workspace, task_id}`, B expects `{task_id}` (422); C expects `plan_json`, B returns `redacted_plan`.
3. No orchestrator (`POST /tasks`, `GET /tasks/{id}`, findings, approval, report).
4. Two divergent plan digests (B `sha256(raw.strip())` vs D canonical JSON) — adopt D's canonical digest.
5. C `/patch` and `/repair` take a client-supplied `workspace` path — the browser must never supply paths.
6. C's patch apply writes directly to a workspace without an approval/digest precondition outside the repair loop.
7. D has no HTTP surface; findings/plan classification/intent unreachable from the app.
8. C's mock adapter has no presets (`502 llm_response_invalid`); real inference unverified.
9. No task state machine; approval is UI-only in mock mode.
10. CORS/proxy hacks (`/service/*` rewrites) exist only because B/C are separate origins.

## 2. Target architecture (single repository, single origin)

```
browser ──> Next.js (app + /api Route Handlers, same origin) ──┬─> worker/  (B: FastAPI 127.0.0.1:8081)
                                                               ├─> ai/      (C: FastAPI 127.0.0.1:8082)
                                                               └─> audit/   (D: FastAPI wrapper 127.0.0.1:8083)
Ollama (gemma4:e4b) <── ai/ only
data/            <- gitignored: worker workspaces + orchestration records
contracts/       <- frozen schemas, unchanged
```

- **Next.js App Router** serves the UI and all application-facing endpoints under
  `web/app/api/*`; browser never talks to B/C/D directly (no CORS dependency).
- **Python kept, not rewritten:** worker (sandboxed terraform/zip/git logic),
  ai (LLM adapters, prompt building, patch parsing/validation, repair loop),
  audit (checkov/opa/plan/intent/regression). Mission allows a local runtime /
  essential Python subprocess to run separately.
- **Orchestration in TypeScript** (`web/lib/server/*`): task state machine,
  task store, workspace resolution, digest verification, approval records,
  report assembly. Server-side only.
- **D gets a thin HTTP wrapper** (`services/audit_api/`) exposing
  `/health`, `/plan/digest`, `/plan/classify`, `/intent`, `/findings`.
  No audit logic is reimplemented.
- **Storage:** worker keeps its own workspace tree (`data/worker/<task_id>/`);
  orchestration keeps `data/orchestration/<task_id>.json`. Server-side code may
  read the workspace (plan JSON, repo) by task id; clients may not.
- **Task ids:** worker-generated 32-hex is authoritative everywhere.
- **Canonical digest:** D `plan_digest(canonical JSON)` over the stored plan JSON,
  surfaced by the audit service; approval is bound to it. B's raw-plan digest is
  recorded as `worker_plan_digest` (informational) and never used for approval.
- **Model:** Ollama `gemma4:e4b` via C's `OllamaAdapter`; `MODEL_BACKEND=ollama`;
  localhost only; explicit `/api/capabilities` reporting; no silent fallback;
  mock mode only behind an explicit flag and labelled in the UI.
- **No apply path:** `terraform apply` is never invoked; patch application only
  writes validated unified diffs inside the workspace with digest+state preconditions.

## 3. Source → target mapping

| Source | Target | Action |
|---|---|---|
| `web/` @ A `569c8da` | `web/` (root Next app) | merge; keep components/lib/tests |
| `worker/` @ B `0507f71` | `worker/` | merge; keep CORS (harmless), fix C client not B |
| `ai/` @ C `da8862d` | `ai/` | merge; fix C→B client payloads; add ollama timeout/temperature config |
| `audit/` @ D `3678880` | `audit/` | merge; add HTTP wrapper under `services/audit_api/` |
| E docs @ `af13e81` | **not merged** | referenced by branch/SHA; findings inform fixes |
| `contracts/` | unchanged | byte-identical guard retained |
| root `.env.example`, README, BUILD_CHANGELOG | rewritten | local-first instructions |

## 4. Conflicts expected

None at merge time: A/B/C/D touch disjoint top-level directories and did not
modify `contracts/`, root README, `.env.example`, or `.gitignore`. Conflicts are
expected only in later hand-edits (e.g. `web/lib/client.ts`), which this
integration owns.

## 5. Decisions

- `D-INT-01` One integration branch `integration/local-consolidation` from `main`;
  each source merge is `--no-ff` and records its SHA.
- `D-INT-02` Orchestration lives in Next.js route handlers; no new Python
  orchestration service. Python stays behind three loopback HTTP services.
- `D-INT-03` Frontend default backend becomes same-origin `/api` (orchestration).
  Mock/direct clients remain for tests/dev behind explicit env flags.
- `D-INT-04` Approval requires: state `AWAITING_APPROVAL`, canonical digest of the
  stored plan, `verify_digest` true, and a human POST. Digest change invalidates.
- `D-INT-05` Findings come from D (checkov + OPA + operational failures) via the
  audit service; missing binaries produce `UnableToVerify`, never `Passed`.
- `D-INT-06` Patch generation uses C server-side; patch application is a separate,
  explicit action with `base_digest` verification and workspace path confinement.
- `D-INT-07` Check selection is server-fixed to the mandatory set
  `fmt,init,validate,plan,show_json`; clients cannot choose a subset.
- `D-INT-08` Local-only: no AWS credentials, no cloud endpoints, no deploy scripts run.

## 6. Execution order

1. Merge D → B → C → A into the integration branch; re-run all suites (baseline).
2. Add audit service wrapper + orchestration store/state machine + `/api` routes.
3. Repoint the frontend to `/api`; remove the `/service/*` rewrite dependency.
4. Fix C→B client payloads; add Ollama env/timeout/temperature handling.
5. Pull `gemma4:e4b`; verify real inference through C (`/capabilities`, requirements,
   patch) and never report mocked output as real.
6. Install local terraform/checkov/opa for real checks; verify fail-closed behavior
   when a tool is missing.
7. Security/contract fixes: digest, approval, patch apply, workspaces, allowlists,
   error mapping, redaction.
8. Tests: unit, contract, tsc, lint, build, Playwright E2E on a safe fixture ZIP.
9. Docs/scripts: `.env.example`, `scripts/setup-local.sh`, `scripts/doctor.sh`,
   root start command, final report with separated test classes.
