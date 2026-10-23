# PlanProof Worker (Agent B)

Execution layer for PlanProof: repository ingestion, sandboxed Terraform check runs,
and redacted plan artifact capture. Owned by Agent B (`worker/`).

## Prerequisites

| Requirement | Needed for | If missing |
|---|---|---|
| Python 3.12 (3.11+ likely works) | service itself | service will not start |
| `terraform` on `PATH` | `fmt`/`init`/`validate`/`plan`/`show_json` checks | every check returns `UnableToVerify`, never `Passed` |
| `git` on `PATH` | `source_type: git_url` ingestion | `POST /ingest` returns `503 GIT_UNAVAILABLE` |
| Network access | `terraform init` provider downloads, `git clone` | corresponding check/clone fails and is reported as `Failed`/`502`, never as success |
| `checkov`, `opa` | **not used here** — owned by Agent D (`audit/`) | n/a |

No cloud credentials are read, passed to child processes, or required. The child
environment is built from an allowlist (`PATH`, `LANG`, `LC_ALL`, `TZ`) plus
service-controlled variables (`HOME`, `TMPDIR`, `TF_IN_AUTOMATION`, `TF_INPUT`,
`GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_ALLOW_PROTOCOL=https`).

## Run locally

```bash
python -m venv .venv && .venv/bin/pip install -r worker/requirements.txt
cd worker
WORKER_DATA_DIR=./workspace-data ../.venv/bin/python -m uvicorn app.main:app --port 8081
```

Health and capability discovery:

```bash
curl localhost:8081/health
curl localhost:8081/capabilities
```

`GET /capabilities` reports detected tool binaries/versions, per-check availability
and argv previews, the sandbox mode, configured limits, and `apply_enabled: false`.

## CORS (browser access)

The worker sends CORS headers so browsers on the configured frontend origin(s) can
call it directly (orchestration mode `NEXT_PUBLIC_API_BASE_URL`).

| Setting | Value |
|---|---|
| Env var | `WORKER_CORS_ALLOW_ORIGINS` (comma-separated, trailing slashes stripped) |
| Default origins | `http://localhost:3000`, `http://127.0.0.1:3000` |
| Methods | `GET`, `POST`, `OPTIONS` |
| Request headers | `Content-Type`, `Authorization` |
| Credentials | not enabled (`allow_credentials=false`); no wildcard ever emitted — a `*` entry in the env var is ignored |
| Preflight | handled by middleware for any path (including missing routes) with `Access-Control-Max-Age: 600` — preflights never 404/405 |
| Error responses | 4xx/5xx carry `Access-Control-Allow-Origin` for approved origins |
| Unapproved origin | no `Access-Control-Allow-Origin` → browser blocks the response (verified in Chromium) |

Alternative path (no CORS needed): the Next.js same-origin proxy
(`/service/worker/:path*` rewrites in `web/next.config.ts`, targets
`PLANPROOF_WORKER_URL` / `NEXT_PUBLIC_WORKER_URL`) — browser talks only to the
frontend origin; the proxy forwards server-side. Direct mode (`/service/worker`)
is verified working; direct cross-origin mode (`NEXT_PUBLIC_API_BASE_URL`) is
verified with the CORS rules above.

The worker never emits `Access-Control-Allow-Origin: *` and does not enable
credentials, so credentialed CORS with wildcards is impossible by construction.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `WORKER_DATA_DIR` | `worker/workspace-data` | root for task workspaces and artifacts |
| `WORKER_TERRAFORM_BIN` | `terraform` | terraform executable name/path |
| `WORKER_GIT_BIN` | `git` | git executable name/path |
| `WORKER_CHECK_TIMEOUT_S` | `300` | per-command timeout; on expiry the process group is killed |
| `WORKER_INGEST_TIMEOUT_S` | `120` | `git clone` timeout |
| `WORKER_MAX_ZIP_BYTES` | `52428800` | max compressed upload size (else `413`) |
| `WORKER_MAX_UNCOMPRESSED_BYTES` | `209715200` | max total extracted size |
| `WORKER_MAX_ZIP_ENTRIES` | `10000` | max archive entries |
| `WORKER_MAX_COMPRESSION_RATIO` | `200` | per-entry compression ratio cap (zip-bomb defense) |
| `WORKER_MAX_OUTPUT_READ_BYTES` | `1000000` | bytes of stdout/stderr read into memory (rest noted as truncated) |
| `WORKER_GIT_ENABLED` | `true` | set `false` to disable git ingestion |

## API

All bodies are validated with Pydantic (`extra` fields rejected). Error details are
`{"detail": {"code": "...", "message": "..."}}` unless noted.

### `POST /ingest`

Accepts JSON:

```json
{"source_type": "zip", "filename": "repo.zip", "zip_base64": "<base64>"}
{"source_type": "git_url", "git_url": "https://example.com/repo.git"}
```

or multipart ZIP upload at `POST /ingest/upload` (field `file`).

Response `200`:

```json
{
  "task_id": "<32 hex chars>",
  "source_type": "zip",
  "tf_files": [{"path": "main.tf", "size_bytes": 123}],
  "providers": [{"name": "aws", "source": "hashicorp/aws", "version": "~> 5.0", "declared_in": "main.tf"}],
  "required_version": ">= 1.5.0",
  "warnings": []
}
```

Provider detection is a heuristic scan of `required_providers` blocks and
`provider "..."` declarations (no full HCL parser).

Status codes:

| Code | Code field | Cause |
|---|---|---|
| 400 | `INVALID_ZIP` | payload is not a ZIP |
| 400 | `UNSAFE_ARCHIVE` | `..`/absolute/backslash path, symlink entry, entry-count, size, or compression-ratio violation |
| 400 | `UNSAFE_GIT_URL` | non-`https://` scheme (`file:`, `ext::`, `ssh:`, ...), whitespace, leading `-` |
| 404 | `TASK_NOT_FOUND` | unknown `task_id` |
| 413 | `PAYLOAD_TOO_LARGE` | upload over `WORKER_MAX_ZIP_BYTES` |
| 422 | (FastAPI validation) | missing/invalid fields, bad base64, bad `task_id` format, unknown check type |
| 502 | `CLONE_FAILED` | `git clone` failed (stderr tail, redacted) |
| 503 | `GIT_UNAVAILABLE` | git binary missing or git disabled |

Failed ingest attempts clean up any partially created task directory. The task
identifier is validated as `^[0-9a-f]{32}$` and always resolved under
`WORKER_DATA_DIR`, so it cannot traverse paths.

### `POST /check`

```json
{"task_id": "<32 hex>", "checks": ["fmt", "validate"]}
```

Valid check types: `fmt`, `init`, `validate`, `plan`, `show_json` (requesting
anything else, including `apply`, is a `422`). Prerequisites are expanded and run
automatically in order: `validate`/`plan` require `init`; `show_json` requires
`plan`.

Fixed argument arrays (the LLM never contributes command strings):

| Check | argv after binary |
|---|---|
| `fmt` | `fmt -check -recursive` |
| `init` | `init -backend=false -input=false -no-color` |
| `validate` | `validate -no-color` |
| `plan` | `plan -input=false -no-color -out=tfplan` |
| `show_json` | `show -json tfplan` |

`terraform apply` is not reachable: it is absent from the registry, rejected by
the runner's binary/subcommand allowlist, and `apply` is not a valid check type.

Response `200`: `{"task_id": "...", "runs": [<CheckRun>...]}` where every run is
validated against `contracts/checkrun.schema.json` before it is returned.

#### Status mapping

| Condition | Status |
|---|---|
| executable not found / not startable | `UnableToVerify` (`exit_code: null`) |
| timeout (process group killed) | `UnableToVerify` |
| killed by signal (crash, output-limit `SIGXFSZ`) | `UnableToVerify` |
| prerequisite check did not pass | `UnableToVerify` + `prerequisite ...` limitation |
| `show_json` requested but `tfplan` missing | `UnableToVerify` |
| exit code 0 | `Passed` |
| any other exit code (tool ran and reported a problem) | `Failed` |

A scanner/tool failure can therefore never be reported as `Passed`. Limitations
are always populated for non-`Passed` runs.

### `POST /capture`

```json
{"task_id": "<32 hex>"}
```

Response `200`:

```json
{"available": true, "plan_digest": "<64 hex>", "redacted_plan": {...}, "captured_at": "...", "truncated": false}
{"available": false, "reason": "no plan artifact available for this task; run the 'plan' check first"}
```

- If `show_json` already ran, the stored plan is returned. If only `plan` ran,
  `show -json` is executed automatically (fixed argv, sandboxed). If terraform is
  unavailable or rendering fails, `available` is `false` with a reason.
- `plan_digest` is `sha256` over the trailing-whitespace-trimmed UTF-8 bytes of
  the raw plan JSON as emitted by `terraform show -json`.
- The raw plan is stored server-side only (`plan.raw.json`, mode `0600`) so the
  digest stays bound to the real plan; the API response contains a deep-redacted
  view (AWS key IDs, secret/token/password-style fields, PEM blocks, bearer
  tokens). Stdout/stderr artifacts are redacted before they are written.

## Data layout

```text
WORKER_DATA_DIR/<task_id>/
  repo/            extracted or cloned Terraform files (mode 0700/0600)
  artifacts/       redacted *.stdout.log/*.stderr.log, plan.raw.json, plan.digest
  home/, tmp/      per-task HOME and TMPDIR for child processes
```

Nothing under `WORKER_DATA_DIR` is served over HTTP except through the redacted
`/capture` response; artifact paths in `CheckRun` are identifiers, not file URLs.

## Sandbox model and limitations

Isolation implemented in-process:

- fixed argv arrays only — no shell, no user-supplied commands, binary
  allowlist enforced in `run_tool` (`SandboxPolicyError` otherwise);
- per-command timeout with process-group `SIGKILL`;
- `RLIMIT_CPU`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`, `RLIMIT_NPROC`, `RLIMIT_CORE=0`;
- environment allowlist (no AWS/credentials variables reach children);
- workspace path confinement (`task_id` pattern + resolution under data dir);
- ZIP path-traversal, absolute-path, symlink, size, entry-count and
  compression-ratio defenses; extracted trees are re-scanned for symlinks;
- `git` restricted to `https://` with `--` before the URL, shallow single-branch
  clone, prompt/system-config disabled, timeout bounded.

**Explicit limitations** (reported in `GET /capabilities`):

- This is not a kernel-level sandbox. Temp dirs plus rlimits do not stop a
  determined malicious repository; **deploy this service inside a disposable
  container/VM with cgroups, seccomp, and network egress controls**.
- Network egress is not restricted here; `terraform init` and `git clone` can
  reach the internet.
- Provider/plugin download failures surface as `Failed` for `init`
  (conservative — never `Passed`), and dependent checks then report
  `UnableToVerify`.
- Provider version parsing is heuristic (regex over `required_providers`).
- `terraform` itself must be installed and validated separately; this repository
  ships mocked-tool tests only.

## Tests

```bash
cd worker && ../.venv/bin/python -m pytest
```

Coverage highlights: valid/invalid fixtures, missing-binary → `UnableToVerify`,
timeout → `UnableToVerify`, crash-by-signal → `UnableToVerify`, ZIP traversal /
symlink / bomb / size / entry-limit attacks, git URL scheme attacks, environment
allowlisting, redaction of artifacts and plan responses, digest stability,
contract validation of live `CheckRun` payloads (positive and negative), static
checks that no `shell=True`/`os.system` exists and that no registry command is
`apply`, and runner rejection of non-allowlisted binaries.

Tests use a fake `terraform`/`git` shim because real binaries are not installed
on this machine; the shim lives only under pytest `tmp_path` and is never
committed.

## Integration requirements (for other agents)

- **Agent A (frontend):** call `POST /ingest` (or `/ingest/upload`), `POST /check`,
  `POST /capture`, `GET /health`, `GET /capabilities`. Only fields defined above
  and in `contracts/` are stable; do not invent fields. `CheckRun.status` values
  are exactly the contract enum.
- **Agent C (AI):** the repair loop must re-run `POST /check` with the **full**
  check list after every patch. The worker does not expose a patch-apply endpoint
  yet — applying unified diffs inside the sandbox needs an agreed interface
  (`POST /tasks/{id}/patch` or similar) that must be coordinated before C writes
  files into `WORKER_DATA_DIR`; direct cross-process writes would break the
  isolation model.
- **Agent D (audit):** plan JSON for classification should be obtained via
  `POST /capture` (`redacted_plan`); the raw artifact is intentionally not
  exposed. `plan_digest` matches the hash D should use when comparing plans.
- **Agent E (review):** safety invariants are asserted in
  `worker/tests/test_safety.py`, `test_checks.py`, and `test_capture.py`.
