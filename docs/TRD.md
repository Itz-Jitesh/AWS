# PlanProof — Technical Requirements Document

## 1. Proposed stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js App Router, React, Tailwind CSS | Pin a currently supported Next.js release after checking hosting compatibility |
| Frontend hosting | AWS Amplify Hosting | Confirm current framework/runtime support before deployment |
| Worker | Python 3.12 + FastAPI, sandboxed subprocesses | Terraform and scanner execution must be isolated |
| AI service | Python + FastAPI, model-agnostic adapter | Keep local and hosted inference behind one interface |
| Model | Intended: Gemma 4 E4B instruction-tuned variant | Verify exact model repository ID, license, access, framework support, and resource needs |
| Model serving | Candidate: SageMaker endpoint with a compatible inference container | Validate the exact container/model combination before relying on it |
| Training | Optional QLoRA experiment on Colab | Do not assume a free T4 is sufficient for the full workflow; test memory and library compatibility |
| Policy | OPA/Rego + Checkov | Normalize all outputs into stable contracts |
| Plan analysis | Custom parser for Terraform plan JSON | Treat plan JSON as sensitive; redact secrets before logs or export |

## 2. Model-serving contract

Keep model serving abstracted behind `LLMAdapter`. The adapter should support either a hosted endpoint that loads an adapter or a separately deployed merged/fine-tuned checkpoint.

Suggested environment variables:

```dotenv
MODEL_BACKEND=ollama
MODEL_MODE=merged
OLLAMA_BASE_URL=http://localhost:11434
SAGEMAKER_ENDPOINT_NAME=
```

Suggested request:

```json
{
  "prompt": "...",
  "diagnostics": "...",
  "max_tokens": 2048
}
```

Suggested normalized response:

```json
{
  "patch": "--- a/main.tf\n+++ b/main.tf\n...",
  "rationale": "...",
  "model_id": "...",
  "finish_reason": "stop"
}
```

**Validation gate:** Do not assume SageMaker DJL/LMI supports LoRA for the selected E4B checkpoint. Test the exact model, container, adapter format, endpoint instance type, request format, and output schema. A merged-model fallback is not automatically compatible with a 4-bit training artifact; document and test the actual export format.

## 3. Shared schemas

All services validate requests and responses against `contracts/*.schema.json`. Schema changes require a version bump and migration note.

## 4. API boundaries

| Endpoint | Owner / caller | Purpose |
|---|---|---|
| `POST /tasks` | Frontend -> API/worker | Create task and return `task_id` |
| `POST /tasks/{id}/check` | AI -> worker | Run full check suite |
| `POST /tasks/{id}/patch` | Frontend -> AI | Generate a proposed patch |
| `POST /tasks/{id}/approve` | Frontend -> orchestration API | Record approval against exact plan digest |
| `GET /tasks/{id}/report` | Frontend -> API/audit | Retrieve evidence report |

For the MVP, these may be separate FastAPI services or a single orchestration API calling internal modules. Keep the contract stable even if deployment topology changes.

## 5. Security boundaries

- Run repository processing in a disposable, isolated workspace/container with CPU, memory, time, process, disk, and network limits.
- Do not rely on a temporary directory alone as a security sandbox.
- The worker must not access host files outside its workspace.
- Map check types to fixed command arrays; the LLM never constructs shell commands.
- Redact secrets before logs, model prompts, artifacts, and reports.
- Never expose cloud credentials to the model.
- Do not run `terraform apply` in the MVP.
- Approval is invalidated if the plan digest changes.
- Treat public Git URLs and ZIP uploads as untrusted input; defend against archive path traversal and malicious repository content.

## 6. Testing

- Unit: schema validation, state transitions, redaction, digest stability.
- Integration: mocked Terraform binary, mocked scanners, mocked LLM.
- Adversarial: patch deletes a resource to silence a finding; scanner crashes; plan changes after approval; malicious ZIP paths; oversized output; timeout.
