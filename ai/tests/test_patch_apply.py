from helpers import BASE_LINES, unified_append, unified_replace
from planproof_ai.contracts import Patch
from planproof_ai.errors import ContextMismatchError, DigestMismatchError
from planproof_ai.patching import apply_patch, validate_patch, workspace_digest


def make_patch(diff: str, digest: str) -> Patch:
    return Patch(
        patch_id="patch-test",
        unified_diff=diff,
        rationale="test patch",
        files_changed=["main.tf"],
        base_digest=digest,
    )


def test_apply_modifies_file(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    patch = make_patch(diff, workspace_digest(workspace))
    written = apply_patch(workspace, patch)
    assert written == ["main.tf"]
    content = open(workspace + "/main.tf", encoding="utf-8").read()
    assert 'bucket = "demo-private"' in content
    assert content.endswith("\n")
    assert "resource" in content


def test_apply_creates_new_file(workspace):
    diff = "--- /dev/null\n+++ b/extra.tf\n@@ -0,0 +1,2 @@\n+resource \"aws_sqs_queue\" \"q\" {\n+}\n"
    patch = Patch(
        patch_id="p-create",
        unified_diff=diff,
        rationale="add queue",
        files_changed=["extra.tf"],
        base_digest=workspace_digest(workspace),
    )
    written = apply_patch(workspace, patch)
    assert written == ["extra.tf"]
    content = open(workspace + "/extra.tf", encoding="utf-8").read()
    assert content == 'resource "aws_sqs_queue" "q" {\n}\n'


def test_apply_rejects_stale_base_digest(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    patch = make_patch(diff, "0" * 64)
    try:
        apply_patch(workspace, patch)
        raise AssertionError("expected DigestMismatchError")
    except DigestMismatchError:
        pass


def test_same_diff_cannot_be_applied_twice(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    patch = make_patch(diff, workspace_digest(workspace))
    apply_patch(workspace, patch)
    try:
        apply_patch(workspace, patch)
        raise AssertionError("expected DigestMismatchError")
    except DigestMismatchError:
        pass
    try:
        validate_patch(workspace, diff)
        raise AssertionError("expected ContextMismatchError")
    except ContextMismatchError:
        pass


def test_append_diff_roundtrip(workspace):
    diff = unified_append("main.tf", BASE_LINES, "# marker")
    patch = make_patch(diff, workspace_digest(workspace))
    apply_patch(workspace, patch)
    content = open(workspace + "/main.tf", encoding="utf-8").read()
    assert content.splitlines()[-1] == "# marker"
    assert content.splitlines()[:3] == BASE_LINES


def test_workspace_digest_is_deterministic(workspace):
    first = workspace_digest(workspace)
    assert first == workspace_digest(workspace)
    with open(workspace + "/main.tf", "a", encoding="utf-8") as fh:
        fh.write("# changed\n")
    assert workspace_digest(workspace) != first


def test_workspace_digest_ignores_git_dir(workspace):
    before = workspace_digest(workspace)
    import os

    os.makedirs(workspace + "/.git", exist_ok=True)
    with open(workspace + "/.git/HEAD", "w", encoding="utf-8") as fh:
        fh.write("ref: refs/heads/main\n")
    assert workspace_digest(workspace) == before
