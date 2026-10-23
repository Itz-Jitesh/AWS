"""Shared fixtures for the audit test suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_executable(directory: Path, name: str, body: str) -> Path:
    """Create an executable script inside ``directory`` (test-local, not committed)."""
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)
    return path


def minimal_finding(**overrides) -> dict:
    base = {
        "schema_version": "1.0.0",
        "finding_id": "fnd_example",
        "rule_source": "checkov",
        "rule_id": "CKV_AWS_18",
        "severity": "high",
        "status": "Failed",
        "title": "S3 access logging",
        "evidence": "resource aws_s3_bucket.logs missing access logging",
        "fingerprint": "a" * 64,
    }
    base.update(overrides)
    return base


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def tmp_bin(tmp_path: Path) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    return directory


@pytest.fixture(autouse=True)
def _clean_scanner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANPROOF_CHECKOV_BIN", raising=False)
    monkeypatch.delenv("PLANPROOF_OPA_BIN", raising=False)
    monkeypatch.delenv("PLANPROOF_CONTRACTS_DIR", raising=False)
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
