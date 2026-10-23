# Step-by-step: What to do next

This guide is ordered to reduce wasted work and avoid unexpected cloud charges.

## Step 1 — Unzip and inspect
1. Download and unzip `planproof.zip`.
2. Open the `planproof/` folder in your editor.
3. Read `README.md`, `docs/PRD.md`, `docs/TRD.md`, and `docs/BOUNDARIES.md`.
4. Treat this as a scaffold: service directories are ownership boundaries, not finished implementations.

## Step 2 — Create a Git repository
From inside the unzipped `planproof/` folder:

```bash
git init
git add .
git commit -m "chore: add PlanProof scaffold and contracts"
```

Create a remote repository if you want cloud backup/PR review, then add it as `origin` and push the initial commit.

## Step 3 — Validate the shared contracts before parallel work
1. Review each schema in `contracts/`.
2. Confirm field names, status enums, severity values, and required evidence fields.
3. Run the JSON syntax check:

```bash
python -m json.tool contracts/finding.schema.json
python -m json.tool contracts/checkrun.schema.json
python -m json.tool contracts/plan-summary.schema.json
python -m json.tool contracts/requirement.schema.json
python -m json.tool contracts/patch.schema.json
```

4. Freeze the contracts in a dedicated commit. If later changes are required, version the schema and document the migration.

## Step 4 — Validate the model route before spending on SageMaker
Do not immediately leave a GPU endpoint running. First:
1. Confirm the exact Gemma model ID exists and is accessible to your account.
2. Confirm its license and allowed usage for the hackathon.
3. Check current AWS SageMaker inference-container support for that exact model architecture and checkpoint format.
4. Check whether the desired endpoint instance can fit the model, context length, quantization, and concurrency you need.
5. Test the simplest supported inference route. Use a local/mock adapter first if the cloud path is not ready.
6. If testing SageMaker, set a budget and billing alerts first, deploy only for the test window, send a tiny request, then delete the endpoint and verify it is gone.
7. Do not assume LoRA works just because a related model family is documented. Test the exact E4B + container + adapter combination.

## Step 5 — Start four builders in parallel
Use separate Git worktrees after the initial commit:

```bash
git worktree add -b agent/a-frontend ../planproof-a
git worktree add -b agent/b-worker   ../planproof-b
git worktree add -b agent/c-ai       ../planproof-c
git worktree add -b agent/d-audit    ../planproof-d
```

Give each agent its matching `agents/agent-*/START_PROMPT.md`. Ask every builder to:
- read `AGENT.md` and the contracts first;
- stay inside their owned directory;
- write tests with the feature;
- avoid modifying shared contracts without coordinating;
- commit small, reviewable changes.

If your agents are external coding agents, create one PR per branch. If they run locally, use separate worktrees and separate agent sessions.

## Step 6 — Keep the reviewer independent
Agent E should review every PR against `AGENT.md`, `docs/BOUNDARIES.md`, and the adversarial tests. Do not ask E to implement features while reviewing; preserve the independent review role.

## Step 7 — Build in this order
1. **Worker + Audit foundations:** ingestion, safe command runner, Checkov/OPA adapters, normalized findings.
2. **Frontend mock workspace:** make the UI render with fixture data before the services are connected.
3. **AI adapter:** mock LLM first, then local model, then hosted model if validated.
4. **Repair loop:** max three attempts; apply only validated unified diffs; run the full suite after each patch.
5. **Plan summary and approval:** parse create/update/replace/delete, compute a stable digest, bind approval to it.
6. **Evidence report:** include versions, check statuses, findings, requirements, plan summary, digest, and known limitations.

## Step 8 — Test safety invariants
Before merging:
- A missing binary or scanner crash returns `UnableToVerify`, never `Passed`.
- A patch cannot delete an unrelated resource just to silence a finding.
- Secrets do not appear in logs, model prompts, or downloadable reports.
- A changed plan digest invalidates previous approval.
- The repair loop reruns all mandatory checks.
- No MVP route can call `terraform apply`.

## Step 9 — Deploy the frontend (only when local demo works)
1. Push the repository to your Git host.
2. Create an Amplify app connected to the repository.
3. Configure the Next.js build settings and required environment variables.
4. Deploy the frontend.
5. Keep worker and AI services private or behind authenticated APIs; do not expose an unauthenticated Terraform runner to the public internet.

## Step 10 — Deploy model inference (only after a successful test)
1. Select a supported model/container/instance combination using current AWS documentation.
2. Deploy for a controlled test window.
3. Confirm health, latency, output parsing, timeout behavior, and cost.
4. Delete the endpoint after testing unless you deliberately need it.
5. Record the validated configuration in `docs/TRD.md`.

## Step 11 — Colab fine-tuning is optional
Do not make QLoRA a prerequisite for the core demo. First build the product with a base model or mock adapter. Fine-tuning should happen only after you have:
- a legally usable model checkpoint;
- a clean, representative repair dataset;
- a validated training script for the model architecture;
- a verified export/deployment format;
- an evaluation set proving improvements over the baseline.

The notebook in `colab/` is a starter outline, not a ready-to-run training guarantee. Follow its README before running cells.

## Step 12 — Rehearse the 3-minute demo
1. Load the seeded insecure Terraform fixture.
2. Show the findings and their evidence.
3. Enter a goal that preserves the existing resource.
4. Generate a patch and inspect the diff.
5. Run the complete checks again.
6. Show the before/after regression comparison.
7. Show the plan summary and any destructive actions.
8. Show approval bound to the plan digest.
9. Export the evidence report.

## Suggested first work session
- [ ] Unzip and inspect files.
- [ ] Create Git repository and first commit.
- [ ] Review/freeze schemas.
- [ ] Assign Agents A–D their directories.
- [ ] Have E prepare adversarial fixtures and review criteria.
- [ ] Use mocks until the core flow is end-to-end.
