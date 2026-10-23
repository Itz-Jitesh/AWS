"""Thin HTTP surface for the deterministic audit library (Agent D).

The service never executes Terraform apply, never invokes a model, and never
accepts arbitrary filesystem paths from clients: workspaces are resolved from
the worker data directory by task id and confined to that root.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from audit import (
    check_intent,
    classify_plan,
    plan_digest,
    run_checkov,
    run_opa,
    verify_digest,
)
from audit.errors import AuditError

VERSION = "0.1.0"
TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")

ROOT = Path(os.environ.get("PLANPROOF_ROOT", Path(__file__).resolve().parents[2]))
WORKER_DATA_DIR = Path(
    os.environ.get("WORKER_DATA_DIR", ROOT / "data" / "worker")
).resolve()

app = FastAPI(title="PlanProof Audit Service (Agent D)", version=VERSION)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanPayload(Strict):
    plan_json: dict[str, Any]


class VerifyPayload(PlanPayload):
    expected: str = Field(min_length=1)


class FindingsPayload(Strict):
    task_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class IntentPayload(Strict):
    requirements: list[dict[str, Any]]
    diff: str = ""
    plan_summary: dict[str, Any] | None = None


def _task_repo(task_id: str) -> Path:
    if not TASK_ID_RE.fullmatch(task_id):
        raise HTTPException(status_code=400, detail={"code": "invalid_task_id", "message": "invalid task id"})
    repo = (WORKER_DATA_DIR / task_id / "repo").resolve()
    try:
        repo.relative_to(WORKER_DATA_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_workspace", "message": "workspace escapes data root"}) from exc
    if not repo.is_dir():
        raise HTTPException(status_code=404, detail={"code": "WORKSPACE_MISSING", "message": f"workspace not found for task {task_id}"})
    return repo


def _load_plan(task_id: str) -> dict[str, Any] | None:
    plan_file = (WORKER_DATA_DIR / task_id / "artifacts" / "plan.raw.json").resolve()
    try:
        plan_file.relative_to(WORKER_DATA_DIR)
    except ValueError:
        return None
    if not plan_file.is_file():
        return None
    try:
        parsed = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _version(argv: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or completed.stderr).strip()
    if not text:
        return None
    if argv[0].endswith("opa"):
        for line in text.splitlines():
            if line.lower().startswith("version"):
                return line.split(":", 1)[1].strip()
    return text.splitlines()[0].strip()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "audit", "version": VERSION}


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    tools = {
        "checkov": {"available": _version(["checkov", "--version"]) is not None, "version": _version(["checkov", "--version"])},
        "opa": {"available": _version(["opa", "version"]) is not None, "version": _version(["opa", "version"])},
    }
    return {
        "status": "ok",
        "service": "audit",
        "version": VERSION,
        "tools": tools,
        "workspace_root": str(WORKER_DATA_DIR),
        "apply_enabled": False,
    }


@app.post("/plan/digest")
def digest(payload: PlanPayload) -> dict[str, str]:
    try:
        return {"plan_digest": plan_digest(payload.plan_json)}
    except AuditError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_plan", "message": str(exc)}) from exc


@app.post("/plan/verify")
def verify(payload: VerifyPayload) -> dict[str, bool]:
    try:
        return {"valid": bool(verify_digest(payload.plan_json, payload.expected))}
    except AuditError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_plan", "message": str(exc)}) from exc


@app.post("/plan/classify")
def classify(payload: PlanPayload) -> dict[str, Any]:
    try:
        return {"plan_summary": classify_plan(payload.plan_json)}
    except AuditError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_plan", "message": str(exc)}) from exc


@app.post("/intent")
def intent(payload: IntentPayload) -> dict[str, Any]:
    try:
        requirements = check_intent(
            payload.requirements, payload.diff, payload.plan_summary
        )
    except AuditError as exc:
        raise HTTPException(status_code=422, detail={"code": "intent_failed", "message": str(exc)}) from exc
    return {"requirements": requirements}


@app.post("/findings")
def findings(payload: FindingsPayload) -> dict[str, Any]:
    repo = _task_repo(payload.task_id)
    plan = _load_plan(payload.task_id)
    records: list[dict[str, Any]] = []
    records.extend(run_checkov(str(repo)))
    records.extend(run_opa(str(repo), plan))
    return {"task_id": payload.task_id, "findings": records, "plan_available": plan is not None}
