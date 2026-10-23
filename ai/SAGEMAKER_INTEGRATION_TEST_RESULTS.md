# SageMaker Integration — Test Results (Agent C)

Generated 2026-10-23 in the Agent C worktree (branch `agent/c-ai`, worktree
`planproof-c`) — **before** any AWS authorization. Every result below is
reproducible with the commands shown.

**Headline:** unit layer fully green (**161 passed / 2 skipped / 0 failed**);
all 2 skipped tests are the live-endpoint tests, skipped because no endpoint,
no credentials, and no cost authorization exist in this environment. **No live
AWS call was made. Nothing involving a real model passed, because nothing
involving a real model was executed.**

---

## 1. Commands and raw results

### 1.1 Full AI suite (current)

```bash
cd ai && .venv/bin/python -m pytest -q
```

```
161 passed, 2 skipped, 1 warning in 0.27s
```

Environment: Python 3.14.6, fastapi 0.161.1, pydantic 2.14.1, pytest 8.x,
jsonschema, httpx — **boto3 NOT installed, AWS CLI absent, no `~/.aws`, no
AWS env vars** (verified earlier in this mission).

### 1.2 Per-file test counts (163 collected)

| file | tests | classification |
|---|---:|---|
| `tests/test_sagemaker_adapter_mocked.py` | 25 | **MOCKED AWS SDK** — fake `invoke_endpoint` client, fake AWS error shapes; zero network |
| `tests/test_capabilities_and_wiring.py` | 22 | **UNIT** (factory selection, `/capabilities` secrecy, env wiring, HTTP error mapping) |
| `tests/test_deploy_guard.py` | 10 | **UNIT** (cost-authorization refusal; AWS client stubbed to fail if touched) |
| `tests/test_sagemaker_live.py` | 2 | **LIVE — SKIPPED/BLOCKED** (§3) |
| `tests/test_llm.py` | 12 | **UNIT** (pre-existing; Mock/Ollama + envelope SageMaker tests via injected `invoke_fn`) |
| `tests/test_app.py` | 10 | **UNIT** (API + frozen-contract validation) |
| `tests/test_repair_loop.py` | 16 | **UNIT** (bounded loop, stop reasons, max 3) |
| `tests/test_patch_validate.py` | 23 | **UNIT** (patch safety matrix) |
| `tests/test_patch_apply.py` | 7 | **UNIT** (dry-run apply engine) |
| `tests/test_contracts.py` | 11 | **UNIT** (contract schema mirrors) |
| `tests/test_clients.py` | 12 | **UNIT** (transport wrappers) |
| `tests/test_extract.py` | 7 | **UNIT** (forces `Unverified`) |
| `tests/test_redaction.py` | 6 | **UNIT** (secret redaction) |
| | **163** | 161 pass + 2 skip |

### 1.3 Failing-test fix (mission item 1)

The regression was a genuine **compatibility break on our side**, not a wrong
contract: while restructuring payload building I left `complete()` calling the
removed `_compose_prompt()` helper (`AttributeError` in 3 envelope tests +
1 prompt-assertion failure). The envelope's documented request shape is
`{prompt, diagnostics, max_tokens, model_id}` with `prompt` and
`diagnostics` as **separate** fields (TRD §2) — the old test's expectation
(`data["prompt"] == "prompt"`, diagnostics sent separately) is correct. Fix:
`complete()` → `_build_payload(request)`; diagnostics are appended into a
combined prompt **only** for `hf`/`openai` modes (single-string inputs).
**No test was weakened to pass** — the implementation was corrected to match
the documented interface.

```bash
.venv/bin/python -m pytest tests/test_llm.py -q
# 12 passed
```

## 2. What the mocked unit coverage proves (and does not)

Proves: payload construction per mode; response parsing/validation per mode;
missing-endpoint and missing-boto3 fail-closed; classification of auth /
credential / throttle / timeout / endpoint / unknown AWS errors into the typed
`llm_*` codes; redaction of AWS error messages *and* outbound prompts;
unknown-backend rejection; explicit mock-vs-sagemaker selection; HTTP error
mapping (503 unavailable / 502 invalid model output / 422 validation) with
`detail.code` preserved; `/capabilities` leaking no credentials; Worker/Audit
env wiring; deploy-script cost gates.

**Does not prove:** that any endpoint exists, that the chosen LMI image serves
`gemma-4-E4B-it`, that our JSON is accepted by it, or that model output is
coherent. Those are §3–§5, all BLOCKED/UNVERIFIED.

## 3. Live endpoint tests — BLOCKED (never executed)

```bash
.venv/bin/python -m pytest tests/test_sagemaker_live.py -q -rs
# 2 skipped
```

Skip reason (from the runner):

```
BLOCKED: live endpoint test disabled. Requires PLANPROOF_RUN_LIVE=1,
SAGEMAKER_ENDPOINT_NAME, and AWS credentials. No endpoint has been deployed
or authorized in this environment.
```

Preconditions unavailable in this environment, itemized: no AWS credentials,
no AWS CLI, no boto3, no deployed endpoint, **no coordinator cost
authorization** (`PLANPROOF_DEPLOY_AUTHORIZED` unset; deploy script refuses —
see `tests/test_deploy_guard.py`, 10 passed).

These tests are **skipped, not passed**. Re-run them per
SAGEMAKER_DEPLOYMENT_PLAN.md §6 after G1–G5, then paste the real output here.

## 4. Serving configuration verification — statically documented, runtime UNVERIFIED

Exact proposed image (`djl-inference:0.38.0-lmi30.0.0-cu130`, DJLServing 0.38
/ LMI 30.0.0 / **vLLM 0.31.0**), alternate vLLM SageMaker DLC
(`vllm:0.31.0-gpu-py312-cu130-ubuntu24.04-sagemaker`), model
`google/gemma-4-E4B-it` (Apache-2.0, not gated), instance `ml.g5.2xlarge`
(1× A10G 24 GB), env sizing, payload/response schemas, memory math, startup
behaviour and context limits: see
[SAGEMAKER_DEPLOYMENT_PLAN.md](SAGEMAKER_DEPLOYMENT_PLAN.md) §1–§2.

Status: **documented from AWS DLC matrix + vLLM Gemma 4 recipe + Google model
card; gates G1–G6 UNVERIFIED at runtime** (no AWS account reachable). Cost
estimate: **$1.52/h** (`ml.g5.2xlarge` us-east-1 On-Demand; ≈ **$3.04** for a
2 h session; ≈$1,110/month if left running) — **not authorized**.

## 5. End-to-end PlanProof integration — BLOCKED (independent of the endpoint)

Even with a live endpoint, e2e cannot pass until the P0 blockers in Agent E's
`PHASE2_BLOCKERS.md` are resolved by their owners — recorded, not worked
around:

1. **C→B 422**: B's `CheckRequest` (`task_id ^[0-9a-f]{32}$`, `checks[]`,
   `extra=forbid`) rejects C's `{workspace, task_id}`; response key is `runs`
   not `checks`; `CaptureRequest` takes only `task_id` and returns
   `redacted_plan`, not `plan_json` (see SAGEMAKER_GEMMA_INTEGRATION.md §5.1).
2. No orchestrator / no `POST /tasks` (frontend entry point missing).
3. No approval backend.
4. Divergent plan digests (DEC-INT-11) and undefined audit HTTP surface
   (DEC-INT-06); patch-apply boundary pending B (DEC-INT-05).

## 6. Milestone report (mission item 6 — honest classification)

| # | milestone | status | evidence |
|---|---|---|---|
| 1 | **Adapter implemented** | ✅ DONE | `planproof_ai/llm/sagemaker.py`, `factory.py`, `config.py`, `app.py`; commit below |
| 2 | **Unit tests passed** | ✅ DONE (MOCKED only) | `161 passed, 2 skipped, 0 failed` — 25 adapter tests use a fake AWS client; **a mocked invocation ≠ a deployed model** |
| 3 | **Serving configuration verified** | ⚠️ **PARTIALLY — static only** | image/vLLM/model/instance/schemas documented + cross-checked from AWS DLC matrix and vLLM recipe; runtime gates G1–G5 **UNVERIFIED** (no AWS account) |
| 4 | **Endpoint deployed** | 🚫 **BLOCKED** | no credentials, no boto3, no coordinator authorization; deploy script refuses without `PLANPROOF_DEPLOY_AUTHORIZED=1` + `--acknowledge-costs` |
| 5 | **Real endpoint inference verified** | 🚫 **BLOCKED** | live tests **skipped**; no real model call ever executed |
| 6 | **PlanProof integration verified end-to-end** | 🚫 **BLOCKED** | P0 blockers above (orchestration, B 422, approval, digest) still open with E/B/D |

**Model choice disclaimer:** integration proceeds with the **base**
`google/gemma-4-E4B-it` because no fine-tuned LoRA artifact exists in this
environment (colab notebook is a placeholder; no Drive link, no weights, no
eval data). This remains subject to successful deployment, evaluation, and the
coordinator supplying the adapter provenance — do not describe the system as
serving a fine-tuned model.

---

*Append post-authorization results (G1–G6 evidence, live pytest output,
endpoint teardown confirmation) below this line.*
