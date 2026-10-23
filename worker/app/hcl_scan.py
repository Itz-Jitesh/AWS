from __future__ import annotations

import re
from pathlib import Path

from .models import ProviderInfo, TfFileInfo

_SKIP_DIRS = {".terraform", ".git", ".planproof", "vendor", "node_modules", "__pycache__"}

_REQUIRED_PROVIDERS_RE = re.compile(r"required_providers\s*{")
_ENTRY_RE = re.compile(r"([A-Za-z_][\w-]*)\s*=\s*{([^{}]*)}")
_SOURCE_RE = re.compile(r'source\s*=\s*"([^"]+)"')
_VERSION_RE = re.compile(r'version\s*=\s*"([^"]+)"')
_PROVIDER_RE = re.compile(r'provider\s+"([^"]+)"')
_REQUIRED_VERSION_RE = re.compile(r'required_version\s*=\s*"([^"]+)"')


def _match_brace_block(text: str, open_index: int) -> str | None:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    return None


def find_tf_files(repo: Path) -> list[TfFileInfo]:
    results: list[TfFileInfo] = []
    for path in sorted(repo.rglob("*.tf")):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        results.append(
            TfFileInfo(path=path.relative_to(repo).as_posix(), size_bytes=path.stat().st_size)
        )
    return results


def scan(repo: Path) -> tuple[list[TfFileInfo], list[ProviderInfo], str | None]:
    tf_files = find_tf_files(repo)
    providers: dict[str, ProviderInfo] = {}
    required_version: str | None = None
    for info in tf_files:
        try:
            text = (repo / info.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _REQUIRED_VERSION_RE.finditer(text):
            required_version = required_version or match.group(1)
        for provider_match in _PROVIDER_RE.finditer(text):
            name = provider_match.group(1)
            providers.setdefault(name, ProviderInfo(name=name, declared_in=info.path))
        for block_match in _REQUIRED_PROVIDERS_RE.finditer(text):
            block = _match_brace_block(text, block_match.end() - 1)
            if block is None:
                continue
            for entry_match in _ENTRY_RE.finditer(block):
                name = entry_match.group(1)
                body = entry_match.group(2)
                source_match = _SOURCE_RE.search(body)
                version_match = _VERSION_RE.search(body)
                existing = providers.get(name)
                providers[name] = ProviderInfo(
                    name=name,
                    source=source_match.group(1) if source_match else (existing.source if existing else None),
                    version=version_match.group(1) if version_match else (existing.version if existing else None),
                    declared_in=info.path,
                )
    return tf_files, list(providers.values()), required_version
