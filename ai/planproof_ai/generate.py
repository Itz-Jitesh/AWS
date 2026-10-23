import re
import uuid

from .config import AIConfig
from .contracts import Patch, Requirement
from .errors import LLMResponseError, PatchValidationError
from .llm.base import LLMAdapter, LLMRequest
from .patching import iter_workspace_files, validate_patch, workspace_digest
from .redaction import redact

_DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)


def extract_diff_text(text: str) -> str | None:
    if not text or not text.strip():
        return None
    stripped = text.strip()
    if stripped.startswith("--- ") or stripped.startswith("diff --git"):
        return stripped
    match = _DIFF_FENCE_RE.search(text)
    if match:
        candidate = match.group(1).strip()
        if candidate.startswith("--- ") or "diff --git" in candidate:
            return candidate
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("--- "):
            tail = "\n".join(lines[idx:]).strip()
            if tail:
                return tail
    return None


def _workspace_file_listing(workspace: str, config: AIConfig) -> str:
    entries = dict(iter_workspace_files(workspace))
    tf_files = [rel for rel in entries if rel.endswith((".tf", ".tf.json"))]
    tf_files.sort()
    out: list[str] = []
    for rel in sorted(entries):
        marker = "" if rel in tf_files else " (non-terraform)"
        out.append(f"FILE {rel}{marker}")
    out.append("")
    for rel in tf_files[: config.max_prompt_workspace_files]:
        with open(entries[rel], encoding="utf-8", errors="replace") as fh:
            content = fh.read(config.max_prompt_file_bytes)
        if len(content.encode("utf-8")) >= config.max_prompt_file_bytes:
            content += "\n... [truncated] ..."
        out.append(f"--- {rel} ---")
        out.append(redact(content))
        out.append("")
    return "\n".join(out)


def build_patch_prompt(workspace: str, requirements: list[Requirement], config: AIConfig) -> str:
    req_lines = []
    for req in requirements:
        flag = "mandatory" if req.mandatory else "optional"
        req_lines.append(f"- [{req.status.value}] ({flag}) {req.text}")
    requirements_block = "\n".join(req_lines) or "- (none)"
    listing = _workspace_file_listing(workspace, config)
    return (
        "You are an infrastructure repair engine for Terraform (HCL) code.\n"
        "Propose the MINIMAL unified diff that advances the requirements below.\n"
        "Rules:\n"
        "- Output ONLY a unified diff (optionally inside a ```diff fence).\n"
        "- Modify only .tf files that already exist in the workspace.\n"
        "- Never delete a file, a resource block, or a prevent_destroy setting.\n"
        "- Never rewrite the whole repository; change only what is required.\n"
        "- Include context lines so the diff applies cleanly.\n"
        "- If no safe change is possible, explain why in plain text instead of outputting a diff.\n\n"
        f"Requirements:\n{requirements_block}\n\n"
        f"Workspace files:\n{listing}"
    )


def generate_patch(
    workspace: str,
    requirements: list[Requirement],
    diagnostics: str,
    *,
    llm: LLMAdapter,
    config: AIConfig | None = None,
) -> Patch:
    config = config or AIConfig()
    base_digest = workspace_digest(workspace)
    prompt = build_patch_prompt(workspace, requirements, config)
    request = LLMRequest(
        prompt=prompt,
        diagnostics=redact(diagnostics),
        max_tokens=config.max_tokens,
    )
    response = llm.complete(request)
    diff_text = response.patch if response.patch and response.patch.strip() else None
    if diff_text is None:
        diff_text = extract_diff_text(response.rationale)
    if not diff_text:
        raise PatchValidationError("model returned no usable unified diff", code="no_diff")
    validated = validate_patch(workspace, diff_text, config.patch)
    rationale = (response.rationale or "").strip()
    if not rationale:
        raise LLMResponseError("model returned an empty rationale")
    return Patch(
        patch_id=f"patch-{uuid.uuid4().hex}",
        unified_diff=diff_text.strip() + "\n",
        rationale=redact(rationale),
        files_changed=validated.changed_paths,
        base_digest=base_digest,
        model_id=response.model_id,
        warnings=[],
    )
