# SageMaker Deployment Plan — Gemma 4 E4B (PlanProof)

**This plan creates paid AWS resources. Nothing may be deployed until the
coordinator explicitly authorizes it** by approving the cost estimate below
and setting `PLANPROOF_DEPLOY_AUTHORIZED=1` (the deploy script also requires
`--acknowledge-costs`; both gates are unit-tested to refuse). No AWS
credentials, AWS CLI, or boto3 exist in the current development environment —
every "runtime" gate here is **UNVERIFIED** until run in an authorized
account.

Research date: 2026-10-23. Static verification only; see
[Verification status](#verification-status-gate-by-gate).

---

## 1. Proposed serving configuration (exact values)

| knob | value | rationale / source |
|---|---|---|
| **Container image** | `763104351884.dkr.ecr.<region>.amazonaws.com/djl-inference:0.38.0-lmi30.0.0-cu130` | AWS Deep Learning Containers "Available Images" matrix: *DJLServing 0.38 · LMI 30.0.0 · **vLLM 0.31.0** · cu130 · SageMaker* |
| **Alternate image** (if LMI path fails) | `763104351884.dkr.ecr.<region>.amazonaws.com/vllm:0.31.0-gpu-py312-cu130-ubuntu24.04-sagemaker` | AWS's purpose-built vLLM SageMaker DLC (same matrix) |
| **vLLM version** | **0.31.0** (bundled in the image) | satisfies the Gemma 4 requirement **vLLM ≥ 0.19.1** (vLLM Gemma 4 recipe) |
| **Model identifier** | `google/gemma-4-E4B-it` | public (not gated), Apache-2.0; downloaded from Hugging Face **at container startup** — no S3 model upload required |
| **Instance** | `ml.g5.2xlarge` × 1 (1× NVIDIA A10G 24 GB, 8 vCPU, 32 GiB) | vLLM: E4B BF16 needs **1× 24 GB+ GPU**; Google lists ≈17.9 GB BF16 incl. overhead → 24 GB is the minimum tier |
| **Container env** (deploy script) | `HF_MODEL_ID=google/gemma-4-E4B-it`, `OPTION_DTYPE=bf16`, `OPTION_MAX_MODEL_LEN=16384`, `OPTION_TENSOR_PARALLEL_DEGREE=1`, `OPTION_GPU_MEMORY_UTILIZATION=0.90` | sized so weights + KV cache fit 24 GB; 16384 is a conservative start (model supports up to 131072 — raise only if KV headroom proves sufficient, see G5) |
| **Endpoint config** | `CreationPendingTimeout=3600`, data capture disabled | first boot downloads ~16 GB of weights (see §4) |
| **Payload mode** | `SAGEMAKER_PAYLOAD_MODE` chosen by gate **G3** (expected `openai` or `hf`) | see §3 — the `planproof` envelope needs a custom formatter |

Orchestration: `deploy/deploy_endpoint.py` (create_model → create_endpoint_config
→ create_endpoint; `status`; `delete`). Direct boto3, no SageMaker SDK
dependency.

## 2. GPU memory / startup / context — documented behaviour

- **Weights:** Gemma 4 E4B BF16 ≈ 15 GB static, ≈17.9 GB with Google's ~20%
  runtime overhead. SFP8 ≈ 8.9 GB; QAT W4A16 checkpoint
  (`google/gemma-4-E4B-it-qat-w4a16-ct`) ≈ 9.8 GB if headroom becomes a
  problem on A10G.
- **KV cache:** 24 GB − 17.9 GB ≈ 6 GB left for KV + activations at BF16 →
  start at `--max-model-len 16384`, `gpu-memory-utilization 0.90`. If the
  container OOMs, reduce context or switch dtype (SFP8) — do **not** silently
  switch instance families without re-approving cost.
- **Startup:** the LMI container pulls the model from Hugging Face on first
  boot; expect **5–20 minutes** to `InService` on a cold endpoint (weights
  ~16 GB + image layers). Failures surface in `describe-endpoint`
  `FailureReason` (auth, OOM, CUDA) — surfaced by `deploy_endpoint.py status`.
- **Context limit:** model card/recipe: up to **131,072** tokens; our prompts
  are small (workspace excerpt ≤ 8 files / 8 KiB per file cap +
  ≤6,000 diagnostics chars), so 16k context is ample for PlanProof traffic.
- **vLLM verification commands** (run inside the endpoint container or via a
  debug instance before/at first deploy):
  ```
  python -c "import vllm; print(vllm.__version__)"   # expect 0.31.0 (>=0.19.1)
  vllm serve google/gemma-4-E4B-it --max-model-len 16384   # standalone equivalent
  ```

## 3. Payload format & response schema (adapter parity)

The adapter (`ai/planproof_ai/llm/sagemaker.py`) supports three modes; the
endpoint must be verified to accept whichever mode we enable (G3):

**A. `openai` mode (expected for LMI + vLLM chat):**
```
→ {"messages":[{"role":"user","content":"<redacted prompt>…"}],
   "max_tokens":2048,"temperature":0,"model":"google/gemma-4-E4B-it"}
← {"choices":[{"message":{"content":"<text>"},"finish_reason":"stop"}], …}
```

**B. `hf` mode (documented LMI text-generation schema, cf. DJL vLLM
tutorial `predict({"inputs": …, "parameters": …})`):**
```
→ {"inputs":"<prompt>\n\nDiagnostics (redacted):\n…",
   "parameters":{"max_new_tokens":2048,"do_sample":false,"return_full_text":false}}
← {"generated_text":"<text>"}   (or [{"generated_text": …}] list form)
```

**C. `planproof` mode (internal TRD §2 envelope — NOT a native LMI format):**
```
→ {"prompt":…,"diagnostics":…,"max_tokens":2048,"model_id":…}
← {"patch":"<unified diff or null>","rationale":…,"model_id":…,"finish_reason":…}
```
Serving the C envelope requires a **custom DJL input/output formatter**
(`serving.properties` `input_formatter`/`output_formatter` shipped as an S3
tarball alongside the model). Two honest options — decide at G3:
1. **No custom code:** run the endpoint in OpenAI or HF format and set
   `SAGEMAKER_PAYLOAD_MODE=openai|hf` for the live integration (all three modes
   are already unit-verified in the adapter).
2. **Keep the internal envelope:** build + test the LMI formatter artifact
   first; `planproof` remains the adapter default for tests either way.

Structured output: prompts ask for a unified diff (plus rationale); the
endpoint is a plain text generator — all structure is re-validated by
`patching.py`, never trusted. `finish_reason` is forwarded, never assumed.

## 4. Verification status (gate by gate)

| # | gate | status |
|---|---|---|
| G1 | Exact image supports Gemma 4 (bundles vLLM 0.31.0 ≥ 0.19.1) | **DOCUMENTED** from AWS DLC matrix + vLLM recipe; confirm at runtime (`vllm.__version__`, model load in container logs). Generic vLLM support alone is *not* treated as proof for this image. |
| G2 | A10G (compute 8.6) runs the cu130 wheels | **UNVERIFIED** — first-deploy risk; if kernels are unsupported, fall back to LMI 25 (`djl-inference:0.36.0-lmi25.0.0-cu130`, vLLM 0.20.1 — still ≥0.19.1) or re-evaluate instance/region with coordinator |
| G3 | Endpoint accepts one of the adapter payload modes | **UNVERIFIED** — single probe invoke per mode after deploy; then set `SAGEMAKER_PAYLOAD_MODE` accordingly |
| G4 | HF startup download works (public repo, no token) | **UNVERIFIED** — watch first `InService`; log any 401/403 (would contradict the `gated:false` finding) |
| G5 | KV-cache headroom at 16k context on 24 GB | **UNVERIFIED** — raise/lower `OPTION_MAX_MODEL_LEN` from OOM evidence |
| G6 | Live adapter round-trip (`tests/test_sagemaker_live.py`) | **BLOCKED** — requires G1–G4 + credentials |

**Do not mark any gate passed from this environment.** Static findings are
citations, not executions.

## 5. Cost estimate (assumptions explicit)

| item | assumption | amount |
|---|---|---|
| `ml.g5.2xlarge`, us-east-1, On-Demand | SageMaker price ≈ **$1.52/h** (Oct 2026 sources; EC2 g5.2xlarge baseline is $1.212/h — SageMaker carries its platform premium, ~+25%) | $1.52 / hour while the endpoint exists |
| short integration session | deploy + probes + live tests + delete ≈ **2 h** | **≈ $3.04** |
| forgotten endpoint, 12 h | overnight | ≈ $18.24 |
| endpoint left up a month | 730 h | ≈ **$1,110** |
| EBS volume | default endpoint storage, ≈$0.12/GB-month (region-dependent) | negligible for a short test |
| S3 model artifacts | base model downloaded from HF by the container — **no upload**; data capture disabled | ≈ $0 |
| data transfer | test traffic only | ≈ $0 |

Caveats: no RI/Spot commitment assumed (SageMaker endpoints are On-Demand);
prices vary by region (e.g. EU regions cost more); delete the endpoint
(`deploy_endpoint.py delete`) to stop billing. **Authorization = coordinator
approves this table and sets `PLANPROOF_DEPLOY_AUTHORIZED=1`.**

## 6. Commands (all post-authorization)

```bash
# 0. once: credentials + extra
aws sts get-caller-identity                      # must succeed
pip install -e 'ai/[aws]'

# 1. deploy (refuses without env gate + --acknowledge-costs)
export PLANPROOF_DEPLOY_AUTHORIZED=1             # set by coordinator
export SAGEMAKER_ROLE_ARN=arn:aws:iam::<acct>:role/<sagemaker-exec-role>
python deploy/deploy_endpoint.py deploy --region us-east-1 \
    --endpoint-name planproof-gemma4-e4b --acknowledge-costs
#  watch until InService (5-20 min):
python deploy/deploy_endpoint.py status --endpoint-name planproof-gemma4-e4b

# 2. probe payload formats (G3), pick SAGEMAKER_PAYLOAD_MODE
# 3. run the LIVE tests (they skip otherwise)
PLANPROOF_RUN_LIVE=1 SAGEMAKER_ENDPOINT_NAME=planproof-gemma4-e4b \
    .venv/bin/python -m pytest tests/test_sagemaker_live.py -m live -v

# 4. point the service at it and exercise /capabilities
export MODEL_BACKEND=sagemaker SAGEMAKER_ENDPOINT_NAME=planproof-gemma4-e4b
export SAGEMAKER_PAYLOAD_MODE=<verified mode> SAGEMAKER_REGION=us-east-1
.venv/bin/python -m uvicorn planproof_ai.app:app --port 8080
curl -s localhost:8080/capabilities | python3 -m json.tool

# 5. TEAR DOWN (stops billing) — required at end of every session
python deploy/deploy_endpoint.py delete --endpoint-name planproof-gemma4-e4b \
    --region us-east-1 --acknowledge-costs
```

**Rollback:** `delete` removes endpoint → endpoint config → model (billing
stops at endpoint deletion; a stuck `Creating` endpoint can be deleted the same
way). No other PlanProof state is touched; `MODEL_BACKEND` reverts to `mock`
by unsetting the endpoint name.

## 7. Post-deployment integration sequence (for the coordinator)

1. G1–G5 evidence collected → set `SAGEMAKER_PAYLOAD_MODE`.
2. Run live tests (G6) → fill SAGEMAKER_INTEGRATION_TEST_RESULTS.md.
3. Resolve the P0 blockers first (E's blockers doc): B↔C `/check`+`/capture`
   shapes, orchestrator, approval backend, canonical digest — **the endpoint
   being up does not make C↔B integration pass**; those remain blocked until
   B/E issue their interface confirmations.
4. If/when the fine-tuned adapter artifact arrives: redeploy with
   `MODEL_MODE=adapter` and re-run evaluation before claiming parity.
