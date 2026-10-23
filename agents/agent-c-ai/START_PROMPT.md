# Agent C — AI

You are Agent C (AI). Work only in `ai/`.

## Build
1. `LLMAdapter` with mock/local Ollama and a validated hosted endpoint backend.
2. `extract_requirements(goal) -> Requirement[]`.
3. `generate_patch(workspace, requirements, diagnostics) -> Patch` using a unified diff only; never rewrite the repo wholesale.
4. `repair_loop(task_id, max_attempts=3)`:
   - call Worker `/check` for the full suite;
   - if all mandatory checks pass and requirements are verified, stop;
   - otherwise send redacted diagnostics to the LLM;
   - validate and apply a safe patch;
   - re-run the full suite after each patch;
   - stop on unsafe patch, regression, or budget exhaustion.
5. Intent check: each requirement ends as `Satisfied`, `Unverified`, or `Violated`; never silently mark `Satisfied`.

## Hard rules
- Never call Terraform directly; use Worker.
- Never suppress a check to make it pass.
- Never send secrets to the model.
- Use an environment variable such as `MODEL_MODE=lora|merged` only after those modes have been tested for the selected model/container.
- Never assume a Gemma variant or serving container supports LoRA without a direct compatibility test.

## Definition of done
A mocked LLM response and mocked Worker produce a patch that fixes one finding without regressing another.
