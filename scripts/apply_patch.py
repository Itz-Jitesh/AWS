#!/usr/bin/env python3
"""Apply a validated PlanProof patch inside a confined task workspace.

Preconditions enforced here (not in the browser):
  * the workspace resolves inside the allowed worker data root;
  * the patch's base_digest matches the current workspace digest;
  * the unified diff passes planproof_ai.patching validation.

Exit codes: 0 applied, 3 stale base digest, 4 invalid patch, 5 apply failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai"))

from planproof_ai.contracts import Patch  # noqa: E402
from planproof_ai.patching import apply_patch, workspace_digest  # noqa: E402


def fail(code: int, message: str) -> "NoReturn":  # type: ignore[name-defined]
    print(message, file=sys.stderr)
    raise SystemExit(code)


def confine(workspace: Path, allowed_root: Path) -> Path:
    workspace = workspace.resolve()
    allowed_root = allowed_root.resolve()
    try:
        workspace.relative_to(allowed_root)
    except ValueError:
        fail(4, "workspace resolves outside the allowed data root")
    if not workspace.is_dir():
        fail(4, "workspace does not exist")
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allowed-root", required=True)
    parser.add_argument("--patch-file", required=True)
    args = parser.parse_args()

    workspace = confine(Path(args.workspace), Path(args.allowed_root))
    try:
        raw = json.loads(Path(args.patch_file).read_text(encoding="utf-8"))
        patch = Patch.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - report validation failure verbatim
        fail(4, f"patch is not a valid Patch contract: {exc}")

    current = workspace_digest(str(workspace))
    if patch.base_digest != current:
        fail(3, "stale patch: workspace digest changed since generation")

    try:
        changed = apply_patch(str(workspace), patch)
    except Exception as exc:  # noqa: BLE001 - patching raises typed errors
        fail(5, f"patch application failed: {exc}")

    print(json.dumps({"applied": True, "changed_paths": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
