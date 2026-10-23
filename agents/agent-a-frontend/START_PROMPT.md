# Agent A — Frontend

You are Agent A (Frontend). Work only in `web/` and read `contracts/` first.

## Stack
Next.js App Router, React, Tailwind CSS. Use TypeScript.

## Build
1. Task creation page: ZIP upload or Git URL, goal textarea, Audit/Build mode selector.
2. Task workspace: requirements panel, findings list, unified diff viewer, plan summary with Create/Update/Replace/Destroy badges, approval button.
3. Typed API client. Until B/C/D are live, use fixtures conforming to `contracts/*.schema.json`.
4. Approval UI must show the plan digest and disable Approve if digest is missing.

## Constraints
- Do not import Python code.
- Do not invent API fields outside the contracts.
- Status labels must be one of `Passed`, `Failed`, `Skipped`, `NotConfigured`, `UnableToVerify`, `AwaitingApproval`.
- Never use “Secure” as a verdict.
- Do not implement live apply in the MVP.

## Definition of done
`npm run build` passes and a demo fixture renders the full workspace with a visible DESTROY badge.
