from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .redact import redact_obj, redact_text
from .store import TaskPaths


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_text_artifact(paths: TaskPaths, name: str, content: str) -> str:
    path = paths.artifacts / name
    path.write_text(redact_text(content), encoding="utf-8")
    os.chmod(path, 0o600)
    return f"{paths.task_id}/artifacts/{name}"


def write_empty_artifact(paths: TaskPaths, name: str) -> str:
    path = paths.artifacts / name
    if not path.exists():
        path.write_text("", encoding="utf-8")
        os.chmod(path, 0o600)
    return f"{paths.task_id}/artifacts/{name}"


def raw_plan_path(paths: TaskPaths) -> Path:
    return paths.artifacts / "plan.raw.json"


def digest_path(paths: TaskPaths) -> Path:
    return paths.artifacts / "plan.digest"


def plan_digest(raw_plan: str) -> str:
    normalized = raw_plan.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def store_plan(paths: TaskPaths, raw_plan: str) -> tuple[str, datetime]:
    raw_path = raw_plan_path(paths)
    raw_path.write_text(raw_plan, encoding="utf-8")
    os.chmod(raw_path, 0o600)
    digest = plan_digest(raw_plan)
    digest_file = digest_path(paths)
    digest_file.write_text(digest + "\n", encoding="utf-8")
    os.chmod(digest_file, 0o600)
    return digest, _utc_now()


def load_plan(paths: TaskPaths) -> tuple[str, str, datetime] | None:
    raw_path = raw_plan_path(paths)
    if not raw_path.is_file():
        return None
    raw_plan = raw_path.read_text(encoding="utf-8")
    stored = digest_path(paths)
    if stored.is_file():
        digest = stored.read_text(encoding="utf-8").strip()
    else:
        digest = plan_digest(raw_plan)
    captured_at = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc)
    return raw_plan, digest, captured_at


def redacted_plan_view(raw_plan: str) -> dict:
    try:
        parsed = json.loads(raw_plan)
    except ValueError:
        return {"redacted": True, "unparsed": True}
    result = redact_obj(parsed)
    if isinstance(result, dict):
        return result
    return {"plan": result}
