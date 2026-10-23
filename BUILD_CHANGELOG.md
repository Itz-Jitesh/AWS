# Build Changelog

## Unreleased

### Day 0 — Contracts and validation
- [ ] Review and freeze `contracts/*.schema.json`
- [ ] Verify exact Gemma model repository ID, license/access, and framework support
- [ ] Verify current SageMaker container and instance compatibility
- [ ] Test a tiny inference request, then delete any temporary endpoint
- [ ] Test LoRA only against the exact chosen model/container combination
- [ ] Configure AWS budget/billing alerts before provisioning

### Day 1 — Foundations
- [ ] Agent B: repository ingestion and sandboxed `terraform fmt/validate`
- [ ] Agent D: Checkov adapter and Finding normalization
- [ ] Agent A: task creation page and typed API client with mocks
- [ ] Agent C: LLM adapter skeleton with mock/local backend

### Day 2 — Core loop
- [ ] Agent D: OPA adapter and regression comparison
- [ ] Agent C: patch generation and bounded repair loop
- [ ] Agent B: `terraform plan -out` and `show -json` capture
- [ ] Agent A: diff viewer and findings list

### Day 3 — Trust layer
- [ ] Agent D: plan classification and intent check
- [ ] Agent A: plan badges (Create/Update/Replace/Destroy) and approval gate
- [ ] Agent E: adversarial fixtures; reject unsafe merges

### Day 4 — Model and demo
- [ ] Optional: Colab QLoRA experiment and artifact upload
- [ ] Agent C: connect validated model endpoint
- [ ] End-to-end demo rehearsal
- [ ] Evidence report export
