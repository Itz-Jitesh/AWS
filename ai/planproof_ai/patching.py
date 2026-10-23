import hashlib
import os
import posixpath
import re

from .config import PatchLimits
from .contracts import Patch
from .errors import (
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

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RESOURCE_HEADER_RE = re.compile(r'^\s*resource\s+"')
SKIP_DIRS = {".git", ".terraform", ".venv", "venv", "__pycache__", "node_modules"}


class Hunk:
    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int, lines: list[str]):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines

    @property
    def added(self) -> int:
        return sum(1 for line in self.lines if line[:1] == "+")

    @property
    def removed_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line[:1] == "-"]


class FilePatch:
    def __init__(self, old_path: str | None, new_path: str | None, hunks: list[Hunk]):
        self.old_path = old_path
        self.new_path = new_path
        self.hunks = hunks

    @property
    def is_create(self) -> bool:
        return self.old_path is None

    @property
    def is_delete(self) -> bool:
        return self.new_path is None

    @property
    def target(self) -> str | None:
        return self.new_path if self.new_path is not None else self.old_path


class ValidatedPatch:
    def __init__(self, files: list[FilePatch], new_contents: dict[str, str]):
        self.files = files
        self.new_contents = new_contents

    @property
    def changed_paths(self) -> list[str]:
        return [fp.target for fp in self.files if fp.target is not None]


def _header_path(raw: str) -> str | None:
    path = raw.split("\t")[0].strip()
    if path == "/dev/null":
        return None
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if path.startswith("./"):
        path = path[2:]
    if path[:2] in ("a/", "b/") and len(path) > 2:
        path = path[2:]
    return path or None


def _parse_hunk(lines: list[str], i: int) -> tuple[Hunk, int]:
    match = HUNK_RE.match(lines[i])
    if not match:
        raise MalformedDiffError(f"invalid hunk header: {lines[i][:60]!r}")
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) is not None else 1
    i += 1
    body: list[str] = []
    old_seen = 0
    new_seen = 0
    total = len(lines)
    while old_seen < old_count or new_seen < new_count:
        if i >= total:
            raise MalformedDiffError("truncated hunk: fewer lines than header declares")
        line = lines[i]
        i += 1
        if line.startswith("\\"):
            continue
        if line == "":
            line = " "
        tag = line[:1]
        content = line[1:]
        if tag == " ":
            old_seen += 1
            new_seen += 1
        elif tag == "-":
            old_seen += 1
        elif tag == "+":
            new_seen += 1
        else:
            raise MalformedDiffError(f"invalid hunk line: {line[:60]!r}")
        if old_seen > old_count or new_seen > new_count:
            raise MalformedDiffError("hunk lines exceed declared counts")
        body.append(tag + content)
    return Hunk(old_start, old_count, new_start, new_count, body), i


def parse_unified_diff(diff_text: str) -> list[FilePatch]:
    if not diff_text or not diff_text.strip():
        raise MalformedDiffError("empty diff")
    text = diff_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    files: list[FilePatch] = []
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if line.startswith("diff --git ") or line.startswith("index ") or line.strip() in ("", "---"):
            i += 1
            continue
        if line.startswith("--- "):
            if i + 1 >= total or not lines[i + 1].startswith("+++ "):
                raise MalformedDiffError("missing '+++' header after '---' header")
            old_path = _header_path(line[4:])
            new_path = _header_path(lines[i + 1][4:])
            if old_path is None and new_path is None:
                raise MalformedDiffError("both sides of file header are /dev/null")
            i += 2
            hunks: list[Hunk] = []
            while i < total:
                if lines[i].startswith("@@ "):
                    hunk, i = _parse_hunk(lines, i)
                    hunks.append(hunk)
                elif lines[i].strip() == "":
                    i += 1
                elif lines[i].startswith("--- ") or lines[i].startswith("diff --git "):
                    break
                else:
                    raise MalformedDiffError(f"unexpected line in file section: {lines[i][:60]!r}")
            if not hunks:
                raise MalformedDiffError(f"no hunks for file header: {old_path or new_path!r}")
            files.append(FilePatch(old_path, new_path, hunks))
            continue
        raise MalformedDiffError(f"unexpected diff line: {line[:60]!r}")
    if not files:
        raise MalformedDiffError("diff contains no file sections")
    return files


def iter_workspace_files(workspace: str) -> list[tuple[str, str]]:
    ws = os.path.realpath(workspace)
    found: list[tuple[str, str]] = []
    for root, dirs, names in os.walk(ws):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, ws).replace(os.sep, "/")
            found.append((rel, full))
    found.sort()
    return found


def workspace_digest(workspace: str) -> str:
    digest = hashlib.sha256()
    for rel, full in iter_workspace_files(workspace):
        file_hash = hashlib.sha256()
        with open(full, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                file_hash.update(chunk)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _normalize_target(workspace: str, path: str | None) -> str:
    if path is None:
        raise PathEscapeError("missing target path")
    if not path or "\0" in path:
        raise PathEscapeError("empty or invalid target path")
    if "\\" in path:
        raise PathEscapeError(f"backslash in path not allowed: {path!r}")
    if path.startswith("/") or os.path.isabs(path):
        raise PathEscapeError(f"absolute path not allowed: {path!r}")
    norm = posixpath.normpath(path.replace(os.sep, "/"))
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        raise PathEscapeError(f"path escapes workspace: {path!r}")
    ws_real = os.path.realpath(workspace)
    resolved = os.path.realpath(os.path.join(ws_real, norm))
    if resolved != ws_real and not resolved.startswith(ws_real + os.sep):
        raise PathEscapeError(f"resolved path escapes workspace: {path!r}")
    return norm


def _check_suffix(norm: str, limits: PatchLimits) -> None:
    if not norm.endswith(limits.allowed_suffixes):
        raise DisallowedFileError(
            f"file type not allowed: {norm!r} (allowed: {', '.join(limits.allowed_suffixes)})"
        )


def _apply_hunks(old_lines: list[str], hunks: list[Hunk], label: str) -> list[str]:
    out: list[str] = []
    pos = 0
    for hunk in hunks:
        start = hunk.old_start - 1 if hunk.old_count > 0 else hunk.old_start
        if start < 0 or start > len(old_lines):
            raise ContextMismatchError(f"hunk start out of range for {label!r}")
        if start < pos:
            raise MalformedDiffError(f"overlapping or out-of-order hunks for {label!r}")
        out.extend(old_lines[pos:start])
        pos = start
        for line in hunk.lines:
            tag = line[:1]
            content = line[1:]
            if tag == " ":
                if pos >= len(old_lines) or old_lines[pos] != content:
                    got = old_lines[pos] if pos < len(old_lines) else "<EOF>"
                    raise ContextMismatchError(
                        f"context mismatch in {label!r} at line {pos + 1}: expected {content!r}, found {got!r}"
                    )
                out.append(content)
                pos += 1
            elif tag == "-":
                if pos >= len(old_lines) or old_lines[pos] != content:
                    got = old_lines[pos] if pos < len(old_lines) else "<EOF>"
                    raise ContextMismatchError(
                        f"removed line does not match {label!r} at line {pos + 1}: expected {content!r}, found {got!r}"
                    )
                pos += 1
            elif tag == "+":
                out.append(content)
    out.extend(old_lines[pos:])
    return out


def _reconstruct_new(hunks: list[Hunk]) -> list[str]:
    out: list[str] = []
    for hunk in hunks:
        for line in hunk.lines:
            if line[:1] in (" ", "+"):
                out.append(line[1:])
    return out


def _join(lines: list[str], trailing_newline: bool) -> str:
    if not lines:
        return ""
    text = "\n".join(lines)
    if trailing_newline:
        text += "\n"
    return text


def _check_destructive(fp: FilePatch, limits: PatchLimits) -> None:
    if limits.allow_resource_removal:
        return
    for hunk in fp.hunks:
        for content in hunk.removed_lines:
            if RESOURCE_HEADER_RE.match(content):
                raise DestructiveChangeError(
                    f"patch deletes a resource block declaration ({content.strip()!r})"
                )
            if "prevent_destroy" in content:
                raise DestructiveChangeError("patch removes a prevent_destroy setting")


def validate_patch(
    workspace: str,
    diff_text: str,
    limits: PatchLimits | None = None,
    expected_digest: str | None = None,
) -> ValidatedPatch:
    limits = limits or PatchLimits()
    if not os.path.isdir(workspace):
        raise BaseMismatchError(f"workspace does not exist: {workspace!r}")
    if len(diff_text.encode("utf-8")) > limits.max_bytes:
        raise PatchTooLargeError(
            f"diff exceeds {limits.max_bytes} bytes (limit max_bytes)"
        )
    files = parse_unified_diff(diff_text)
    if len(files) > limits.max_files:
        raise TooManyFilesError(f"diff touches {len(files)} files (limit {limits.max_files})")
    changed = sum(h.added + len(h.removed_lines) for fp in files for h in fp.hunks)
    if changed > limits.max_changed_lines:
        raise PatchTooLargeError(f"diff changes {changed} lines (limit {limits.max_changed_lines})")
    if expected_digest is not None and workspace_digest(workspace) != expected_digest:
        raise DigestMismatchError("workspace digest does not match patch base_digest")

    ws_real = os.path.realpath(workspace)
    new_contents: dict[str, str] = {}
    for fp in files:
        if fp.is_delete:
            raise FileDeletedError(f"patch deletes file {fp.old_path!r}; file deletion is not allowed")
        norm = _normalize_target(workspace, fp.target)
        _check_suffix(norm, limits)
        _check_destructive(fp, limits)
        full = os.path.join(ws_real, norm)
        if fp.is_create:
            if os.path.exists(full):
                raise BaseMismatchError(f"cannot create {norm!r}: file already exists")
            old_content = None
        else:
            old_norm = _normalize_target(workspace, fp.old_path)
            if old_norm != norm:
                raise MalformedDiffError(f"renames are not supported: {fp.old_path!r} -> {fp.new_path!r}")
            if not os.path.isfile(full):
                raise BaseMismatchError(f"target file not found in workspace: {norm!r}")
            with open(full, encoding="utf-8") as fh:
                old_content = fh.read()
        new_contents[norm] = _render_new_content(old_content, fp, norm)
    return ValidatedPatch(files, new_contents)


def _render_new_content(old_content: str | None, fp: FilePatch, label: str) -> str:
    if old_content is None:
        if any(h.old_count > 0 for h in fp.hunks):
            raise ContextMismatchError(f"create patch for {label!r} has removals")
        lines = _reconstruct_new(fp.hunks)
        return _join(lines, trailing_newline=bool(lines))
    old_lines = old_content.splitlines()
    trailing = old_content.endswith("\n")
    out = _apply_hunks(old_lines, fp.hunks, label)
    return _join(out, trailing_newline=trailing and bool(out))


def apply_patch(workspace: str, patch: Patch, limits: PatchLimits | None = None) -> list[str]:
    limits = limits or PatchLimits()
    validated = validate_patch(workspace, patch.unified_diff, limits, expected_digest=patch.base_digest)
    written: list[str] = []
    ws_real = os.path.realpath(workspace)
    for norm, content in validated.new_contents.items():
        full = os.path.join(ws_real, norm)
        os.makedirs(os.path.dirname(full) or ws_real, exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        written.append(norm)
    return sorted(written)
