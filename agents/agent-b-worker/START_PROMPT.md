# Agent B — Worker

You are Agent B (Worker). Work only in `worker/`.

Build a FastAPI service exposing:
- `POST /ingest`: accept ZIP or Git URL; return workspace identifier, detected `.tf` files, and provider versions.
- `POST /check`: run fixed, allowlisted checks and return `CheckRun[]`.
- `POST /capture`: return a redacted plan JSON artifact.

Checks may include `terraform fmt -check`, `terraform init -backend=false`, `terraform validate`, `terraform plan -out=tfplan`, and `terraform show -json tfplan`, subject to a safe sandbox and fixture support.

## Hard rules
- The LLM never supplies shell strings. Map check types to fixed argument arrays.
- Use a disposable isolated sandbox with resource/time limits; a temp directory alone is not a security boundary.
- Do not allow access to host files outside the workspace.
- Redact secret-like values before returning output.
- Missing binaries return `UnableToVerify`, never `Passed`.
- Do not run `terraform apply` in the MVP.
- Treat Git URLs and ZIP contents as untrusted.

## Definition of done
A deliberately broken `.tf` file returns `Failed` for validate; a valid fixture returns `Passed`; a missing Terraform binary returns `UnableToVerify`.
