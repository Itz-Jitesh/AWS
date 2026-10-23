# PlanProof

PlanProof is an AI infrastructure engineering harness for auditing Terraform, proposing minimal repairs, re-running deterministic checks, classifying infrastructure plan changes, and requiring human approval before any apply operation.

## Quick start

1. Read `docs/PRD.md`, `docs/TRD.md`, and `docs/BOUNDARIES.md`.
2. Follow `docs/STEP_BY_STEP.md` before creating cloud resources.
3. Freeze the contracts in `contracts/` before parallel implementation.
4. Give each builder only their assigned directory and start prompt.
5. Keep Agent E as an independent reviewer; do not let it silently change production code.
6. Start with mock/local services. Validate cloud model serving separately before committing to paid resources.

## Repository map

- `AGENT.md` — multi-agent protocol and merge rules
- `docs/` — product, technical, roadmap, boundaries, and setup guide
- `contracts/` — shared JSON Schemas used across agent boundaries
- `agents/` — per-agent task prompts
- `web/`, `worker/`, `ai/`, `audit/` — implementation ownership boundaries
- `colab/` — training notebook placeholder and dataset guidance
- `BUILD_CHANGELOG.md` — day-by-day build checklist

## Important implementation note

The supplied plan is a scaffold, not a validated deployment recipe. In particular, confirm the exact Gemma 4 model ID, license/access terms, Transformers support, SageMaker container support, GPU memory requirements, and LoRA compatibility before training or provisioning. Treat all model-serving assumptions as Day-0 validation tasks.
