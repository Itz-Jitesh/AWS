"""Strict validation against the shared ``contracts/`` JSON Schemas.

The schemas are the frozen interface between agents. This module only reads
them; it never writes or relaxes them. Every payload emitted by the audit
library is validated against schema version 1.0.0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from .errors import ContractValidationError

SCHEMA_NAMES = ("checkrun", "finding", "patch", "plan-summary", "requirement")
_SCHEMA_FILES = {name: f"{name}.schema.json" for name in SCHEMA_NAMES}

_VALIDATORS: dict[tuple[str, str], Draft202012Validator] = {}


def contracts_dir() -> Path:
    """Directory holding the shared schemas (overridable for tests)."""
    override = os.environ.get("PLANPROOF_CONTRACTS_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "contracts"


def load_schema(name: str) -> dict[str, Any]:
    """Load one shared schema by contract name, e.g. ``"finding"``."""
    if name not in _SCHEMA_FILES:
        raise ContractValidationError(
            f"unknown contract {name!r}; expected one of {sorted(SCHEMA_NAMES)}"
        )
    path = contracts_dir() / _SCHEMA_FILES[name]
    try:
        with path.open(encoding="utf-8") as handle:
            schema = json.load(handle)
    except FileNotFoundError as exc:
        raise ContractValidationError(f"shared schema not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"shared schema is not valid JSON: {path}: {exc}") from exc
    Draft202012Validator.check_schema(schema)
    return schema


def _validator(name: str) -> Draft202012Validator:
    key = (name, str(contracts_dir()))
    validator = _VALIDATORS.get(key)
    if validator is None:
        validator = Draft202012Validator(load_schema(name))
        _VALIDATORS[key] = validator
    return validator


def is_valid(instance: Any, name: str) -> bool:
    """Return whether ``instance`` satisfies the named contract."""
    return _validator(name).is_valid(instance)


def validate(instance: Any, name: str) -> None:
    """Raise :class:`ContractValidationError` when ``instance`` is invalid."""
    errors = sorted(_validator(name).iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return
    details = "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors[:5]
    )
    raise ContractValidationError(f"{name} payload failed contract validation: {details}")


def validate_all(instances: Iterable[Mapping[str, Any]], name: str) -> None:
    """Validate every element of ``instances`` against the named contract."""
    for index, instance in enumerate(instances):
        try:
            validate(instance, name)
        except ContractValidationError as exc:
            raise ContractValidationError(f"item {index}: {exc}") from exc
