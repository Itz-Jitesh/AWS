# SageMaker ↔ Gemma 4 Integration (Agent C)

**Status:** adapter implemented and unit-verified; live endpoint BLOCKED
(no AWS credentials, no boto3, no coordinator cost authorization in this
environment). Model = **base `google/gemma-4-E4B-it`** (Strategy A) — the
fine-tuned LoRA artifact does not exist anywhere accessible (see
[Artifact status](#artifact-status)).

Everything below is in `ai/` on branch `agent/c-ai`. Tests: **161 passed,
2 skipped (live, BLOCKED), 0 failed** — commands and per-file counts in
[SAGEMAKER_INTEGRATION_TEST_RESULTS.md](SAGEMAKER_INTEGRATION_TEST_RESULTS.md).

---

## 1. Adapter implementation

`planproof_ai/llm/sagemaker.py` — `SageMakerAdapter(LLMAdapter)` speaks the
real SageMaker Runtime API via boto3:

- **Invocation:** lazy `boto3.client("sagemaker-runtime").invoke_endpoint(
  EndpointName=…, ContentType="application/json", Accept="application/json",
  Body=json)`, with `botocore.config.Config(connect_timeout=min(t,10),
  read_timeout=SAGEMAKER_TIMEOUT_S, retries={"max_attempts": 1})`.
  boto3 is imported only on first use; if it is missing, the adapter raises
  `ModelNotConfiguredError` (fail-closed — it never silently degrades to a
  mock). Tests inject `invoke_client`/`invoke_fn`; no test touches AWS.
- **Payload modes** (`SAGEMAKER_PAYLOAD_MODE`, validated at construction;
  unknown value → `ValueError`, no coercion):

  | mode | request JSON | parsed response |
  |---|---|---|
  | `planproof` (default) | `{prompt, diagnostics, max_tokens, model_id}` (TRD §2 envelope, prompt+diagnostics redacted) | `{patch?, rationale, model_id?, finish_reason?}`; also accepts LMI `{generation}` fallback → `rationale` |
  | `hf` | `{inputs: "<prompt>\n\nDiagnostics (redacted):…", parameters: {max_new_tokens, do_sample:false, return_full_text:false}}` | `{generated_text}` (or `{generated_text:[{generated_text}]}` list form) |
  | `openai` | `{messages:[{role:user,content}], max_tokens, temperature:0, model}` | `{choices[0].message.content}` or `{choices[0].text}` |

  The default `planproof` mode keeps the pre-existing envelope contract and
  all original unit tests green. **Which mode the real endpoint accepts is a
  pre-deploy verification gate** (G3 in the deployment plan) — the envelope is
  not a native LMI format.
- **Response validation:** non-JSON / non-object / missing required key per
  mode → `LLMResponseError` (`llm_response_invalid`) with a redacted message.
- **Error taxonomy** — every SDK/transport exception is classified from
  `exc.response["Error"]["Code"]` (duck-typed, no botocore import needed) and
  exception class names, then redacted:

  | mapped error | code | triggers (examples) |
  |---|---|---|
  | `LLMAuthError` | `llm_auth_error` | `AccessDeniedException`, `ExpiredToken`, `InvalidClientTokenId`, `NoCredentialsError`, `PartialCredentialsError` |
  | `LLMTimeoutError` | `llm_timeout` | `ReadTimeoutError`, `ConnectTimeoutError`, `RequestTimeout`, class name contains `Timeout` |
  | `LLMThrottledError` | `llm_throttled` | `ThrottlingException`, `TooManyRequestsException`, `ProvisionedThroughputExceededException` |
  | `LLMEndpointError` | `llm_endpoint_error` | `EndpointNotFoundException`, `ModelNotReady`, `ServiceUnavailable`, `ValidationException`, **and any unknown error (fail-closed default)** |

  All subclass `LLMUnavailableError` → HTTP **503** from the API (502 only for
  well-formed-but-invalid model output). AWS error text passes through
  `redact()` (AWS key patterns, `secret_access_key=…`, bearer tokens, generic
  `token=/password=/api_key=` assignments) — verified by test
  `test_aws_error_details_are_redacted`.
- **Fail-closed configuration** (`llm/factory.py`):
  - `MODEL_BACKEND` set → used verbatim; unknown value →
    `ModelNotConfiguredError` (never an implicit mock).
  - empty backend → `sagemaker` iff `SAGEMAKER_ENDPOINT_NAME` set, else `mock`.
  - explicit `MODEL_BACKEND=mock` wins even if an endpoint name is present.
  - `MODEL_BACKEND=sagemaker` with empty endpoint → adapter constructs (so
    `/capabilities` can report `endpoint_configured: false`) but `complete()`
    raises `ModelNotConfiguredError` with the validation gate text.

### Configuration (`.env.example` documents all of these)

| env var | default | meaning |
|---|---|---|
| `MODEL_BACKEND` | (auto) | `mock` / `ollama` / `sagemaker`; empty = auto |
| `SAGEMAKER_ENDPOINT_NAME` | — | required for real inference |
| `SAGEMAKER_REGION` | `AWS_REGION`/`AWS_DEFAULT_REGION` | endpoint region |
| `SAGEMAKER_PAYLOAD_MODE` | `planproof` | `planproof` / `hf` / `openai` |
| `SAGEMAKER_TIMEOUT_S` | `120` | invoke read timeout |
| `MODEL_ID` | `google/gemma-4-E4B-it` (sagemaker) | reported model id |
| `MODEL_MODE` | `merged` | weights provenance (`merged` until LoRA provenance exists) |
| `WORKER_BASE_URL` / `AUDIT_BASE_URL` | empty = mock | peer wiring |
| `LLM_MAX_TOKENS` / `MAX_REPAIR_ATTEMPTS` | 2048 / 3 (hard cap) | limits |

## 2. Observable capability reporting

`GET /capabilities` (new, additive — no frozen contract changed):

```json
{"status":"ok",
 "model":{"backend":"sagemaker","adapter":"SageMakerAdapter",
          "model_id":"google/gemma-4-E4B-it","model_mode":"merged",
          "payload_mode":"planproof","endpoint_name":"…",
          "endpoint_configured":true,"requires_live_endpoint":true},
 "worker":{"mode":"http|mock","base_url":…},
 "audit":{"mode":"http|mock","base_url":…},
 "repair_max_attempts":3}
```

- No secrets, credentials, ARNs or account ids are echoed (tested with fake
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in env).
- `/health.model_backend` now reports the **resolved** backend.
- Worker/Audit wiring: `WORKER_BASE_URL`/`AUDIT_BASE_URL` set →
  `HttpWorkerClient`/`HttpAuditClient`; empty → in-process mocks. Explicitly
  injected clients take precedence. (Fixes DEC-INT-12 for wiring; `uvicorn`
  added to `requirements.txt`; `boto3` is the `aws` extra in `pyproject.toml`.)

## 3. Safety architecture unchanged

Extraction still forces `Unverified`; patch validation (malformed hunks, path
escape, non-`.tf`, deletion, digest mismatch, size/file/line limits,
`prevent_destroy` removal) is untouched; repair capped at 3 with the same stop
reasons; diagnostics/prompts redacted before they reach any model; nothing in
`ai/` runs `terraform`; audit status codes `Passed|Failed|Skipped|
NotConfigured|UnableToVerify` preserved; no silent mock fallback anywhere.

## 4. Model and artifact status

| fact | value | source |
|---|---|---|
| target model | `google/gemma-4-E4B-it` (base `google/gemma-4-E4B`) | vLLM Gemma 4 recipe; HF API Phase 2 |
| license / gating | Apache-2.0, **not gated** (no HF token required) | HF API `gated: False` |
| size | dense ≈8B total (effective 4B, PLE embeddings) | vLLM recipe / Google model card |
| memory (BF16) | ≈15 GB weights, ≈17.9 GB incl. ~20% runtime overhead; SFP8 ≈8.9 GB; Q4_0 ≈4.5 GB | Google Gemma 4 overview |
| context | 131,072 tokens | vLLM recipe (`--max-model-len` ≤ 131072) |
| vLLM support | **vLLM ≥ 0.19.1**; dedicated Gemma 4 recipe, `vllm/vllm-openai:gemma4` images | docs.vllm.ai Gemma 4 recipe |

### Artifact status (why Strategy A)

- `colab/train_gemma4_e4b_qlora.ipynb` is a **placeholder**: `MODEL_ID=
  'REPLACE_WITH_VERIFIED_MODEL_ID'`, no dataset, no `output_dir`, no training
  outputs; `colab/README.md` contains no Drive link.
- Repo-wide search found no adapter/`.safetensors`/PEFT files, no Drive URL,
  no eval data, no model card for a fine-tune.
- Therefore the initial integration deploys the **base instruct model** with
  `MODEL_MODE=merged`. The choice remains subject to: (a) coordinator supplying
  the fine-tuned adapter + base model id + adapter config + eval results, and
  (b) a successful deployment/evaluation. Do not describe the current design
  as serving a fine-tuned model.

## 5. Integration boundaries (documented, not worked around)

### 5.1 C→B mismatches (live 422, Agent E P0 #3)

Evidence: `worker/app/models.py` + `worker/app/main.py` (worktree B),
`agents/agent-e-reviewer/PHASE2_BLOCKERS.md`.

| # | C sends today | B actually requires / returns | Effect |
|---|---|---|---|
| 1 | `POST /check` body `{workspace, task_id}` (any id string) | `CheckRequest {task_id: ^[0-9a-f]{32}$, checks: [CheckType]}`, `extra="forbid"` | **422** (unknown `workspace`; id pattern; missing `checks`) |
| 2 | reads response key `checks` | responds `{task_id, runs}` | would `KeyError`/treat as failure even after 422 fixed |
| 3 | `POST /capture` body `{workspace, task_id}` | `CaptureRequest {task_id}` only | **422** |
| 4 | reads `plan_json` | returns `{available, plan_digest, redacted_plan, …}` | capture unusable from C |

Resolution is an **interface decision pending** (DEC-INT-01/02/04/06, owners
E/B/D/coordinator). Per instructions: NOT rewritten unilaterally — `HttpWorkerClient`
still implements the documented TRD §4 proposal, tests use `MockWorkerClient`,
and `README.md` + this section record the authoritative mismatch. We do not
bypass the Worker or write into its workspace.

### 5.2 Other frozen boundaries (unchanged)

- **Patch apply** must go through B (`POST /tasks/{id}/patch/apply`,
  DEC-INT-05) — `ai/` only validates + dry-runs in memory.
- **Plan digest** divergence (DEC-INT-11): use D's canonical digest at
  integration time; C does not invent one.
- **Audit HTTP surface** (DEC-INT-06) undefined → `AuditClient` stays a
  protocol + mock; `AUDIT_BASE_URL` wiring exists but is unexercised.
- **Orchestration/approval** (P0): no orchestrator, no approval backend —
  `POST /tasks/{id}/repair` remains explicitly *provisional*.
- **Contracts** `schema_version 1.0.0` untouched; non-nullable
  `notes/description/reason` still serialized omit-None everywhere.

## 6. Deliverables

| file | purpose |
|---|---|
| `planproof_ai/llm/sagemaker.py` | real adapter (this doc §1) |
| `planproof_ai/llm/factory.py` | explicit, fail-closed backend selection |
| `planproof_ai/config.py` | new env config (§1 table) |
| `planproof_ai/app.py` | `/capabilities` + env wiring (§2) |
| `deploy/deploy_endpoint.py` | guarded endpoint lifecycle (cost gate) |
| `.env.example` | full configuration reference |
| `SAGEMAKER_DEPLOYMENT_PLAN.md` | exact image/vLLM/instance/schema + gates + costs |
| `SAGEMAKER_INTEGRATION_TEST_RESULTS.md` | commands, results, mock-vs-live, milestones |
| `tests/test_sagemaker_adapter_mocked.py` | 25 mocked-SDK unit tests |
| `tests/test_capabilities_and_wiring.py` | 22 factory/wiring/error-mapping tests |
| `tests/test_deploy_guard.py` | 10 cost-authorization guard tests |
| `tests/test_sagemaker_live.py` | 2 live tests, **skipped/BLOCKED** |
