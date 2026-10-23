from __future__ import annotations

import io
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .config import Settings
from .redact import redact_text
from .sandbox import ToolResult, run_tool

_SYMLINK_MASK = 0o170000
_SYMLINK_TYPE = 0o120000


class UnsafeArchiveError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GitUnavailableError(Exception):
    pass


class GitCloneError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def validate_git_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise UnsafeArchiveError("git_url is empty")
    if any(char.isspace() for char in cleaned):
        raise UnsafeArchiveError("git_url contains whitespace")
    if cleaned.startswith("-"):
        raise UnsafeArchiveError("git_url must not start with '-'")
    lowered = cleaned.lower()
    if not lowered.startswith("https://"):
        raise UnsafeArchiveError("git_url must use https://")
    if "\x00" in cleaned:
        raise UnsafeArchiveError("git_url contains a NUL byte")
    if len(cleaned) > 2048:
        raise UnsafeArchiveError("git_url is too long")
    return cleaned


def _entry_name_error(name: str) -> str | None:
    if not name or name.strip() == "":
        return "archive contains an entry with an empty name"
    if "\x00" in name:
        return "archive entry name contains a NUL byte"
    if "\\" in name:
        return f"archive entry name contains a backslash: {name!r}"
    if ":" in name:
        return f"archive entry name contains a colon: {name!r}"
    normalized = name[:-1] if name.endswith("/") else name
    if normalized.startswith("/"):
        return f"archive entry has an absolute path: {name!r}"
    if len(normalized) >= 2 and normalized[1] == ":":
        return f"archive entry has a drive-qualified path: {name!r}"
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        return f"archive entry escapes the workspace: {name!r}"
    return None


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def inspect_archive(archive: zipfile.ZipFile, settings: Settings) -> None:
    infos = archive.infolist()
    if not infos:
        raise UnsafeArchiveError("archive is empty")
    if len(infos) > settings.max_zip_entries:
        raise UnsafeArchiveError(
            f"archive has {len(infos)} entries, exceeding the limit of {settings.max_zip_entries}"
        )
    total_declared = 0
    for info in infos:
        error = _entry_name_error(info.filename)
        if error:
            raise UnsafeArchiveError(error)
        if _is_symlink_entry(info):
            raise UnsafeArchiveError(
                f"archive entry is a symlink, which is not allowed: {info.filename!r}"
            )
        if stat.S_ISDIR(info.external_attr >> 16):
            continue
        total_declared += info.file_size
        if total_declared > settings.max_uncompressed_bytes:
            raise UnsafeArchiveError(
                "archive uncompressed size exceeds "
                f"the limit of {settings.max_uncompressed_bytes} bytes"
            )
        if info.compress_size > 0 and info.file_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > settings.max_compression_ratio:
                raise UnsafeArchiveError(
                    f"archive entry {info.filename!r} compression ratio {ratio:.0f} exceeds "
                    f"the limit of {settings.max_compression_ratio}"
                )


def extract_archive(zip_bytes: bytes, dest: Path, settings: Settings) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("payload is not a valid ZIP archive") from exc
    with archive:
        inspect_archive(archive, settings)
        dest_real = os.path.realpath(dest)
        total_read = 0
        try:
            for info in archive.infolist():
                error = _entry_name_error(info.filename)
                if error:
                    raise UnsafeArchiveError(error)
                if _is_symlink_entry(info):
                    raise UnsafeArchiveError(
                        f"archive entry is a symlink, which is not allowed: {info.filename!r}"
                    )
                target = dest / info.filename
                target_real = os.path.realpath(target)
                if target_real != dest_real and not target_real.startswith(dest_real + os.sep):
                    raise UnsafeArchiveError(
                        f"archive entry resolves outside the workspace: {info.filename!r}"
                    )
                if info.is_dir() or info.filename.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as handle:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        total_read += len(chunk)
                        if total_read > settings.max_uncompressed_bytes:
                            raise UnsafeArchiveError(
                                "archive expanded beyond the uncompressed size limit"
                            )
                        handle.write(chunk)
                os.chmod(target, 0o600)
        except zipfile.BadZipFile as exc:
            raise UnsafeArchiveError("archive is corrupt") from exc
    _reject_symlinks_on_disk(dest)


def _reject_symlinks_on_disk(dest: Path) -> None:
    for root, dirs, files in os.walk(dest, followlinks=False):
        for name in list(dirs) + list(files):
            path = Path(root) / name
            if path.is_symlink():
                raise UnsafeArchiveError(
                    f"extracted entry is a symlink, which is not allowed: {path.name!r}"
                )


def clone_repo(url: str, dest: Path, settings: Settings) -> ToolResult:
    if not settings.git_enabled:
        raise GitUnavailableError("git ingestion is disabled")
    if shutil.which(settings.git_bin) is None:
        raise GitUnavailableError(f"{settings.git_bin} executable not found")
    argv = [
        settings.git_bin,
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--",
        url,
        str(dest),
    ]
    result = run_tool(
        settings,
        argv,
        cwd=dest.parent,
        workspace=dest.parent,
        timeout_s=settings.ingest_timeout_s,
        stdout_path=dest.parent / "artifacts" / "git.stdout.log",
        stderr_path=dest.parent / "artifacts" / "git.stderr.log",
        allowed_binaries={settings.git_bin},
    )
    if result.spawn_error:
        raise GitUnavailableError(f"{settings.git_bin} executable not available")
    if result.timed_out:
        raise GitCloneError("clone timed out")
    if result.killed_by_signal:
        raise GitCloneError(f"clone terminated by signal {result.signal_name}")
    if result.exit_code != 0:
        tail = redact_text(result.stderr_text.strip()[-500:])
        raise GitCloneError(tail or f"clone exited with code {result.exit_code}")
    return result
