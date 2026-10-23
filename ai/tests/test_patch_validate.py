import os

import pytest

from helpers import BASE_LINES, unified_replace
from planproof_ai.config import PatchLimits
from planproof_ai.errors import (
    BaseMismatchError,
    ContextMismatchError,
    DestructiveChangeError,
    DigestMismatchError,
    DisallowedFileError,
    FileDeletedError,
    MalformedDiffError,
    PathEscapeError,
    PatchTooLargeError,
    PatchValidationError,
    TooManyFilesError,
)
from planproof_ai.patching import validate_patch, workspace_digest


def test_valid_diff_validates(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    result = validate_patch(workspace, diff)
    assert result.changed_paths == ["main.tf"]
    assert 'bucket = "demo-private"' in result.new_contents["main.tf"]


def test_empty_diff_rejected(workspace):
    with pytest.raises(MalformedDiffError):
        validate_patch(workspace, "   ")


def test_non_diff_text_rejected(workspace):
    with pytest.raises(MalformedDiffError):
        validate_patch(workspace, "please fix the bucket, thanks")


def test_bad_hunk_header_rejected(workspace):
    diff = "--- a/main.tf\n+++ b/main.tf\n@@ bogus @@\n+ x\n"
    with pytest.raises(MalformedDiffError):
        validate_patch(workspace, diff)


def test_truncated_hunk_rejected(workspace):
    diff = "--- a/main.tf\n+++ b/main.tf\n@@ -1,10 +1,10 @@\n context\n"
    with pytest.raises(MalformedDiffError):
        validate_patch(workspace, diff)


def test_path_escape_dotdot_rejected(workspace):
    diff = "--- a/../evil.tf\n+++ b/../evil.tf\n@@ -1,1 +1,1 @@\n-x\n+y\n"
    with pytest.raises(PathEscapeError):
        validate_patch(workspace, diff)


def test_absolute_path_rejected(workspace):
    diff = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1,1 +1,1 @@\n-x\n+y\n"
    with pytest.raises(PathEscapeError):
        validate_patch(workspace, diff)


def test_symlink_escape_rejected(workspace, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.tf"
    outside.write_text('resource "aws_s3_bucket" "x" {\n}\n', encoding="utf-8")
    os.symlink(outside, os.path.join(workspace, "link.tf"))
    diff = "--- a/link.tf\n+++ b/link.tf\n@@ -1,2 +1,3 @@\n resource \"aws_s3_bucket\" \"x\" {\n-}\n+  region = \"us-east-1\"\n+}\n"
    with pytest.raises(PathEscapeError):
        validate_patch(workspace, diff)


def test_disallowed_suffix_rejected(workspace):
    diff = "--- a/setup.sh\n+++ b/setup.sh\n@@ -1,1 +1,1 @@\n-x\n+y\n"
    with pytest.raises(DisallowedFileError):
        validate_patch(workspace, diff)


def test_file_deletion_rejected(workspace):
    diff = "--- a/main.tf\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-resource \"aws_s3_bucket\" \"b\" {\n-  bucket = \"demo\"\n-}\n"
    with pytest.raises(FileDeletedError):
        validate_patch(workspace, diff)


def test_digest_mismatch_rejected(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "x"')
    with pytest.raises(DigestMismatchError):
        validate_patch(workspace, diff, expected_digest="0" * 64)


def test_correct_digest_accepted(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "x"')
    result = validate_patch(workspace, diff, expected_digest=workspace_digest(workspace))
    assert "main.tf" in result.new_contents


def test_patch_too_large_bytes(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    with pytest.raises(PatchTooLargeError):
        validate_patch(workspace, diff, limits=PatchLimits(max_bytes=10))


def test_too_many_files_rejected(workspace):
    diff = (
        unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "x"')
        + "--- /dev/null\n+++ b/new.tf\n@@ -0,0 +1,1 @@\n+resource \"aws_sqs_queue\" \"q\" {}\n"
    )
    with pytest.raises(TooManyFilesError):
        validate_patch(workspace, diff, limits=PatchLimits(max_files=1))


def test_too_many_changed_lines(workspace):
    diff = unified_replace("main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"')
    with pytest.raises(PatchTooLargeError):
        validate_patch(workspace, diff, limits=PatchLimits(max_changed_lines=1))


def test_resource_block_deletion_rejected(workspace):
    diff = (
        "--- a/main.tf\n+++ b/main.tf\n@@ -1,3 +1,2 @@\n"
        '-resource "aws_s3_bucket" "b" {\n'
        ' bucket = "demo"\n'
        " }\n"
    )
    with pytest.raises(DestructiveChangeError):
        validate_patch(workspace, diff)


def test_prevent_destroy_removal_rejected(tmp_path):
    tf = tmp_path / "main.tf"
    tf.write_text(
        'resource "aws_s3_bucket" "b" {\n  bucket = "demo"\n  lifecycle {\n    prevent_destroy = true\n  }\n}\n',
        encoding="utf-8",
    )
    lines = tf.read_text(encoding="utf-8").splitlines()
    diff = (
        "--- a/main.tf\n+++ b/main.tf\n@@ -1,6 +1,5 @@\n"
        ' resource "aws_s3_bucket" "b" {\n'
        '   bucket = "demo"\n'
        "   lifecycle {\n"
        "-    prevent_destroy = true\n"
        "   }\n"
        " }\n"
    )
    assert len(lines) == 6
    with pytest.raises(DestructiveChangeError):
        validate_patch(str(tmp_path), diff)


def test_context_mismatch_rejected(workspace):
    diff = (
        "--- a/main.tf\n+++ b/main.tf\n@@ -1,3 +1,3 @@\n"
        ' resource "aws_s3_bucket" "b" {\n'
        '-  bucket = "wrong"\n'
        '+  bucket = "demo-private"\n'
        " }\n"
    )
    with pytest.raises(ContextMismatchError):
        validate_patch(workspace, diff)


def test_missing_target_file_rejected(workspace):
    diff = (
        "--- a/missing.tf\n+++ b/missing.tf\n@@ -1,1 +1,1 @@\n"
        "-x\n+y\n"
    )
    with pytest.raises(BaseMismatchError):
        validate_patch(workspace, diff)


def test_create_existing_file_rejected(workspace):
    diff = "--- /dev/null\n+++ b/main.tf\n@@ -0,0 +1,1 @@\n+resource \"aws_s3_bucket\" \"c\" {}\n"
    with pytest.raises(BaseMismatchError):
        validate_patch(workspace, diff)


def test_rename_rejected(workspace):
    diff = (
        "--- a/main.tf\n+++ b/renamed.tf\n@@ -1,3 +1,3 @@\n"
        ' resource "aws_s3_bucket" "b" {\n'
        '   bucket = "demo"\n'
        " }\n"
    )
    with pytest.raises(MalformedDiffError):
        validate_patch(workspace, diff)


def test_hunk_out_of_range_rejected(workspace):
    diff = (
        "--- a/main.tf\n+++ b/main.tf\n@@ -99,1 +99,1 @@\n"
        "-x\n+y\n"
    )
    with pytest.raises(ContextMismatchError):
        validate_patch(workspace, diff)


def test_validation_error_codes_are_stable(workspace):
    with pytest.raises(PatchValidationError) as excinfo:
        validate_patch(workspace, "garbage")
    assert excinfo.value.code == "malformed_diff"
    with pytest.raises(PatchValidationError) as excinfo:
        validate_patch(workspace, "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-x\n+y\n")
    assert excinfo.value.code == "path_escape"
