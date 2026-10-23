# MVP Boundaries

## Allowed
- Terraform HCL for AWS infrastructure.
- `fmt`, `validate`, `plan`, `show -json`.
- Checkov + OPA.
- A model accessed through the `LLMAdapter`, locally or through a validated hosted endpoint.
- Single-user, single-project demo.

## Forbidden in MVP
- Applying infrastructure by default.
- LLM-generated shell commands.
- Storing cloud secrets in prompts.
- Claiming “secure” after a clean scan.
- Supporting CloudFormation/Pulumi.
- Multi-tenant auth.
- Autonomous retries beyond three attempts.
- Changing policy rules to make a check pass.
- Marking missing/crashed scanners as passed.
