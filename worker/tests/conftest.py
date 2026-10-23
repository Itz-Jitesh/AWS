from __future__ import annotations

import base64
import io
import os
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.main import create_app

VALID_MAIN_TF = """terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "demo" {
  bucket = "planproof-demo-public"
  acl    = "public-read"
}
"""

INVALID_MAIN_TF = """resource "aws_s3_bucket" "broken" {
  bucket =
INVALID
}
"""

FAKE_TERRAFORM_TEMPLATE = '''
import json, os, pathlib, signal, sys, time

BEHAVIOR = "__BEHAVIOR__"


def tf_content():
    chunks = []
    for path in sorted(pathlib.Path(".").rglob("*.tf")):
        if ".terraform" in path.parts or ".git" in path.parts:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\\n".join(chunks)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "version":
        print("Terraform 1.9.5 (fake)")
        return 0
    try:
        pathlib.Path("envdump.json").write_text(json.dumps(dict(os.environ), indent=2))
    except OSError:
        pass
    if BEHAVIOR == "hang":
        time.sleep(120)
        return 0
    if BEHAVIOR == "crash":
        os.kill(os.getpid(), signal.SIGKILL)
    content = tf_content()
    if cmd == "fmt":
        return 1 if "BADFMT" in content else 0
    if cmd == "init":
        if "BADINIT" in content:
            print("Error: init failed", file=sys.stderr)
            return 1
        pathlib.Path(".terraform").mkdir(exist_ok=True)
        return 0
    if cmd == "validate":
        if "INVALID" in content:
            print("Error: Invalid value", file=sys.stderr)
            return 1
        return 0
    if cmd == "plan":
        if BEHAVIOR == "plan_nowrite":
            return 0
        pathlib.Path("tfplan").write_bytes(b"fake-plan-binary")
        print("Plan: 1 to add, 0 to change, 0 to destroy.")
        return 0
    if cmd == "show":
        if not pathlib.Path("tfplan").exists():
            print("Error: no plan file", file=sys.stderr)
            return 1
        payload = {
            "format_version": "1.2",
            "terraform_version": "1.9.5",
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_s3_bucket.demo",
                            "mode": "managed",
                            "type": "aws_s3_bucket",
                            "name": "demo",
                            "values": {
                                "bucket": "planproof-demo-public",
                                "acl": "public-read",
                                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                                "secret_access_key": "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"
                            }
                        }
                    ]
                }
            },
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.demo",
                    "type": "aws_s3_bucket",
                    "change": {"actions": ["create"], "before": None, "after": {"acl": "public-read"}}
                }
            ]
        }
        print(json.dumps(payload))
        return 0
    print("unknown command: " + cmd, file=sys.stderr)
    return 2


sys.exit(main())
'''

FAKE_GIT_BODY = '''
import json, pathlib, sys

args = sys.argv[1:]
try:
    pathlib.Path("git.calls.json").write_text(json.dumps(args))
except OSError:
    pass
if args[:1] == ["--version"]:
    print("git version 2.49.0 (fake)")
    sys.exit(0)
if args[:1] == ["clone"]:
    url = args[-2]
    dest = args[-1]
    if "fail-clone" in url:
        print("fatal: repository not found", file=sys.stderr)
        sys.exit(128)
    dest_path = pathlib.Path(dest)
    dest_path.mkdir(parents=True, exist_ok=True)
    (dest_path / "main.tf").write_text(
        'terraform {\\n'
        '  required_providers {\\n'
        '    aws = {\\n'
        '      source  = "hashicorp/aws"\\n'
        '      version = "~> 5.0"\\n'
        '    }\\n'
        '  }\\n'
        '}\\n\\n'
        'provider "aws" {\\n'
        '  region = "us-east-1"\\n'
        '}\\n'
    )
    (dest_path / ".git").mkdir(exist_ok=True)
    sys.exit(0)
sys.exit(0)
'''


def build_zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class WorkerTestEnv:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.bin_dir = tmp_path / "bin"
        self.bin_dir.mkdir()
        self.data_dir = tmp_path / "data"
        self.monkeypatch.setenv("PATH", str(self.bin_dir))

    def install_terraform(self, behavior: str = "pass") -> Path:
        return self._write_script(
            self.bin_dir / "terraform",
            FAKE_TERRAFORM_TEMPLATE.replace("__BEHAVIOR__", behavior),
        )

    def install_git(self) -> Path:
        return self._write_script(self.bin_dir / "git", FAKE_GIT_BODY)

    def set_path(self, entries: list[str]) -> None:
        self.monkeypatch.setenv("PATH", os.pathsep.join(entries))

    @staticmethod
    def _write_script(path: Path, body: str) -> Path:
        path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def make_settings(self, **overrides) -> Settings:
        base = dict(
            data_dir=self.data_dir,
            check_timeout_s=30,
            ingest_timeout_s=30,
            version_probe_timeout_s=10,
        )
        base.update(overrides)
        settings = Settings(**base)
        settings.ensure_dirs()
        return settings

    def client(self, **overrides) -> TestClient:
        return TestClient(create_app(self.make_settings(**overrides)))

    def task_dirs(self) -> list[Path]:
        if not self.data_dir.is_dir():
            return []
        return [entry for entry in self.data_dir.iterdir() if entry.is_dir()]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkerTestEnv:
    return WorkerTestEnv(tmp_path, monkeypatch)
