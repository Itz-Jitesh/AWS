# Agent C — AI Service (`ai/`)

Model abstraction, requirements extraction, patch generation, and the bounded
repair loop for PlanProof. Python 3.11+ / FastAPI / Pydantic v2.

## Layout

```
ai/
  planproof_ai/
    contracts.py     Pydantic mirrors of contracts/*.schema.json (read-only)
    config.py        AIConfig / PatchLimits (env-driven)
    errors.py        Typed error hierarchy with stable error codes
    redaction.py     Secret redaction for prompts/diagnostics
    llm/             LLMAdapter, MockLLMAdapter, OllamaAdapter, SageMakerAdapter
    extract.py       extract_requirements(goal) -> Requirement[]
    patching.py      diff parse / validate / apply + workspace digest
    generate.py      generate_patch(workspace, requirements, diagnostics) -> Patch
    repair.py        repair_loop(task_id, workspace, ...) -> RepairResult
    clients.py       WorkerClient / AuditClient protocols + HTTP wrappers
    testing.py       MockWorkerClient, MockAuditClient, fixture builders
    app.py           FastAPI app factory + typed request/response models
  tests/             pytest suite (no network, no live model, no terraform)
  README.md          This file: interface contract for Agent C
```

Run tests: `ai/.venv/bin/python -m pytest` from `ai/`.

## Task 1 — Interface documentation (AI ⇄ Worker ⇄ Audit)

These are the interfaces Agent C consumes. None of them change the frozen
schemas in `contracts/`.

### AI → Worker (owned by Agent B)

Programmatic boundary (`AGENT.md`): `run_check_suite(workspace, task_id) -> CheckRun[]`.

HTTP mapping (proposed, mirrors TRD §4 `POST /tasks/{id}/check`):

| Endpoint | Body | Response |
|---|---|---|
| `POST /check` | `{"workspace": "<path>", "task_id": "..."}` | `{"checks": [CheckRun, ...]}` |
| `POST /capture` | `{"workspace": "<path>", "task_id": "..."}` | `{"plan_json": {...}}` (redacted plan artifact, optional) |

Failure semantics required from B:

- Missing/crashed tool → a `CheckRun` with status `UnableToVerify` (never `Passed`).
- Transport/HTTP failure → AI treats the run as `WORKER_FAILURE` and stops the
  loop; it never fabricates checks.

Typed wrappers live in `clients.py` (`HttpWorkerClient`); tests use
`testing.MockWorkerClient`.

### AI → Audit (owned by Agent D)

Pure-function boundary per `AGENT.md`:

- `check_intent(requirements, diff, plan_summary) -> Requirement[]`
  (statuses only `Satisfied | Unverified | Violated`, evidence attached)
- `classify_plan(workspace, plan_json) -> PlanSummary`
- `compare(before, after) -> RegressionResult` — Phase 2; the AI loop currently
  detects regressions from `CheckRun` transitions (see below).

`RegressionResult` in `contracts.py` is a **provisional local type**, not a
frozen contract; it must be aligned with D's real signature before integration.
Tests use `testing.MockAuditClient`.

### Frontend → AI (TRD §4)

| Endpoint | Body | Response |
|---|---|---|
| `POST /tasks/{id}/requirements` | `{"goal": "..."}` | `{"requirements": [Requirement, ...]}` |
| `POST /tasks/{id}/patch` | `{"workspace", "goal"?, "requirements"?, "diagnostics"?}` | `{"patch": Patch}` or `422 {"code", "message"}` |
| `POST /tasks/{id}/repair` | `{"workspace", "goal"?, "requirements"?, "max_attempts" ≤ 3}` | `{"result": RepairResult}` — **provisional** orchestration endpoint |
| `GET /health` | — | `{"status": "ok", "model_backend": ...}` |

### AI → LLM (TRD §2)

- `LLMRequest {prompt, diagnostics, max_tokens}`
- `LLMResponse {patch, rationale, model_id, finish_reason}`

Adapters: `MockLLMAdapter` (tests/demo), `OllamaAdapter` (local, optional),
`SageMakerAdapter` (interface only; raises `ModelNotConfigured` until a hosted
endpoint passes the TRD §2 validation gate — no AWS resources are created here).

## Design decisions

- **Requirement statuses**: extraction always forces `Unverified`. A model claim
  of `Satisfied` is discarded; only audit evidence may set `Satisfied`.
- **Patch safety**: every diff is parsed and dry-run applied in memory before
  touching disk. Rejected: malformed hunks, path escape (`..`, absolute,
  symlink), non-`.tf` targets, file deletion, size/file/line limits exceeded,
  `base_digest` mismatch, resource-block deletion, `prevent_destroy` removal,
  context mismatch. Limitations configurable via `PatchLimits`.
- **Workspace digest**: sha256 over sorted relative paths + per-file sha256 of
  all files excluding `.git/`, `.terraform/`, `.venv/`, `__pycache__/`.
- **Repair loop**: `min(max_attempts, 3)` hard cap (BOUNDARIES). Stop reasons:
  `resolved`, `requirements_not_met`, `unsafe_patch`, `regression`,
  `attempts_exhausted`, `worker_failure`, `audit_failure`, `intent_violated`.
  Regression = any `Passed` check that later is missing or not `Passed`.
  The full suite is re-run after every applied patch; diagnostics are redacted
  before they reach any model.
- **No apply path**: nothing in `ai/` invokes `terraform`; all Terraform calls
  go through Worker.

## Model-serving notes (Phase 1 constraint)

Model IDs, endpoint names, and `MODEL_MODE` are configuration only. Before
enabling `sagemaker` backend, validate: exact model repo ID + license,
Transformers/LoRA support for that checkpoint, chosen SageMaker container
(LoRA vs merged), instance type memory, request/response schema parity with
`LLMResponse`, then delete any temporary endpoint. Do not assume Gemma 4 E4B
supports a given LoRA serving configuration.
