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
    llm/             LLMAdapter, MockLLMAdapter, OllamaAdapter, SageMakerAdapter (real boto3 path)
    extract.py       extract_requirements(goal) -> Requirement[]
    patching.py      diff parse / validate / apply + workspace digest
    generate.py      generate_patch(workspace, requirements, diagnostics) -> Patch
    repair.py        repair_loop(task_id, workspace, ...) -> RepairResult
    clients.py       WorkerClient / AuditClient protocols + HTTP wrappers
    testing.py       MockWorkerClient, MockAuditClient, fixture builders
    app.py           FastAPI app factory (/health, /capabilities, /tasks/...)
  deploy/            guarded SageMaker endpoint lifecycle (cost-authorized)
  tests/             pytest suite (no network, no terraform; live tests skip-gated)
  .env.example       configuration reference
  SAGEMAKER_*.md     integration, deployment plan, test results
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
| `GET /health` | — | `{"status": "ok", "model_backend": <resolved>, ...}` |
| `GET /capabilities` | — | model backend/adapter/endpoint_configured/payload_mode + worker/audit `mock|http` modes (no secrets) |

### AI → LLM (TRD §2)

- `LLMRequest {prompt, diagnostics, max_tokens}`
- `LLMResponse {patch, rationale, model_id, finish_reason}`

Adapters: `MockLLMAdapter` (tests/demo), `OllamaAdapter` (local, optional),
`SageMakerAdapter` (**real SageMaker Runtime path**: boto3 `invoke_endpoint`,
payload modes `planproof|hf|openai`, typed auth/timeout/throttle/endpoint
errors with redacted messages, fail-closed when unconfigured — **no silent
mock fallback**). Live inference requires a deployed endpoint; see
[SAGEMAKER_DEPLOYMENT_PLAN.md](SAGEMAKER_DEPLOYMENT_PLAN.md).

Run the service:

```bash
pip install -r requirements.txt        # + pip install -e '.[aws]' for boto3
.venv/bin/python -m uvicorn planproof_ai.app:app --port 8080
```

Configuration reference: [.env.example](.env.example). Key variables:
`MODEL_BACKEND` (empty = auto: endpoint implies `sagemaker`, else `mock`;
unknown value fails closed), `SAGEMAKER_ENDPOINT_NAME`, `SAGEMAKER_REGION`,
`SAGEMAKER_PAYLOAD_MODE`, `SAGEMAKER_TIMEOUT_S`, `MODEL_ID`,
`MODEL_MODE`, `WORKER_BASE_URL`, `AUDIT_BASE_URL`.

## SageMaker / Gemma 4 docs

- [SAGEMAKER_GEMMA_INTEGRATION.md](SAGEMAKER_GEMMA_INTEGRATION.md) — adapter,
  capabilities, artifact status (base model = Strategy A), C→B mismatches.
- [SAGEMAKER_DEPLOYMENT_PLAN.md](SAGEMAKER_DEPLOYMENT_PLAN.md) — exact LMI
  image / vLLM version / instance / schemas, verification gates, costs,
  authorization gates, teardown.
- [SAGEMAKER_INTEGRATION_TEST_RESULTS.md](SAGEMAKER_INTEGRATION_TEST_RESULTS.md)
  — commands, results, mock-vs-live classification, milestone report.

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

The validation gate text lives in `llm/sagemaker.py::VALIDATION_GATE` and is
raised as `ModelNotConfiguredError` whenever real inference is attempted
without a configured endpoint/boto3. The fine-tuned LoRA artifact is currently
unavailable in this repository (colab notebook is a placeholder); the
integration therefore targets the **base** `google/gemma-4-E4B-it` with
`MODEL_MODE=merged`, subject to later evaluation.
