# Roadmap

| Phase | Goal | Exit criterion |
|---|---|---|
| 0 | Contracts and model-serving validation | A test request returns a normalized response from the selected model path, or a documented fallback is chosen |
| 1 | Read-only audit | A demo Terraform repository produces normalized findings |
| 2 | Generation and repair | A patch fixes at least one issue without introducing a regression |
| 3 | Plan and approval | Destructive actions are surfaced; approval is tied to the plan digest |
| 4 | Hosting (stretch) | Demo UI is hosted and health-checked |
| 5 | Expansion | CloudFormation, drift, cost, PR comments |

**Hackathon commitment:** Phases 0–3. Attempt Phase 4 only if the core safety and demo path is stable.
