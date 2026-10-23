from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def contract_dump(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)


class CheckStatus(str, Enum):
    PASSED = "Passed"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    NOT_CONFIGURED = "NotConfigured"
    UNABLE_TO_VERIFY = "UnableToVerify"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


class RuleSource(str, Enum):
    CHECKOV = "checkov"
    OPA = "opa"
    TERRAFORM = "terraform"
    CUSTOM = "custom"


class RequirementStatus(str, Enum):
    SATISFIED = "Satisfied"
    UNVERIFIED = "Unverified"
    VIOLATED = "Violated"


class PlanAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    NO_OP = "no-op"


class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckRun(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    check_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    status: CheckStatus
    started_at: datetime
    duration_ms: int = Field(ge=0)
    summary: str
    exit_code: int | None = None
    tool_version: str | None = None
    stdout_artifact: str | None = None
    stderr_artifact: str | None = None
    limitations: list[str] = Field(default_factory=list)


class Finding(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    finding_id: str = Field(min_length=1)
    rule_source: RuleSource
    rule_id: str = Field(min_length=1)
    severity: Severity
    status: CheckStatus
    title: str = Field(min_length=1)
    description: str | None = None
    resource_address: str | None = None
    file_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    evidence: str = Field(min_length=1)
    remediation: str | None = None
    fingerprint: str = ""


class Requirement(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    requirement_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    mandatory: bool
    status: RequirementStatus
    evidence: list[str] = Field(default_factory=list)
    notes: str | None = None


class Patch(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    patch_id: str = Field(min_length=1)
    unified_diff: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    files_changed: list[str] = Field(min_length=1)
    base_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DestructiveAction(ContractModel):
    address: str
    actions: list[PlanAction]
    risk: RiskLevel
    reason: str | None = None


class PlanSummary(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    create: int = Field(ge=0)
    update: int = Field(ge=0)
    replace: int = Field(ge=0)
    destroy: int = Field(ge=0)
    destructive_actions: list[DestructiveAction] = Field(default_factory=list)
    has_changes: bool


class RegressionResult(ContractModel):
    """Provisional local type. Not a frozen contract — must be aligned with
    Agent D's `compare(before, after)` signature before integration."""

    regressed: list[Finding] = Field(default_factory=list)
    resolved: list[Finding] = Field(default_factory=list)
    unchanged_count: int = Field(ge=0, default=0)
    is_regression: bool = False
