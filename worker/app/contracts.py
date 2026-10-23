from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker, ValidationError, validate

from .models import CheckRun

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contracts"


@lru_cache(maxsize=1)
def checkrun_schema() -> dict[str, Any]:
    path = SCHEMA_DIR / "checkrun.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def finding_schema() -> dict[str, Any]:
    path = SCHEMA_DIR / "finding.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _format_checker() -> FormatChecker:
    return FormatChecker()


def validate_checkrun_payload(payload: dict[str, Any]) -> None:
    validate(instance=payload, schema=checkrun_schema(), format_checker=_format_checker())


def validate_checkrun(run: CheckRun) -> None:
    validate_checkrun_payload(run.model_dump(mode="json"))


class ContractViolation(RuntimeError):
    pass


def ensure_contract(run: CheckRun) -> CheckRun:
    try:
        validate_checkrun(run)
    except ValidationError as exc:
        raise ContractViolation(f"CheckRun violates checkrun.schema.json: {exc.message}") from exc
    return run
