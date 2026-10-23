from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

CheckStatus = Literal["Passed", "Failed", "Skipped", "NotConfigured", "UnableToVerify"]

CheckType = Literal["fmt", "init", "validate", "plan", "show_json"]

TASK_ID_PATTERN = "^[0-9a-f]{32}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckRun(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    check_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    status: CheckStatus
    started_at: AwareDatetime
    duration_ms: int = Field(ge=0)
    summary: str
    exit_code: int | None = None
    tool_version: str | None = None
    stdout_artifact: str | None = None
    stderr_artifact: str | None = None
    limitations: list[str] = Field(default_factory=list)


class TfFileInfo(StrictModel):
    path: str
    size_bytes: int = Field(ge=0)


class ProviderInfo(StrictModel):
    name: str
    source: str | None = None
    version: str | None = None
    declared_in: str | None = None


class IngestZipRequest(StrictModel):
    source_type: Literal["zip"]
    filename: str | None = Field(default=None, max_length=255)
    zip_base64: str

    @field_validator("zip_base64")
    @classmethod
    def decode_zip(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("zip_base64 is not valid base64") from exc
        if not decoded:
            raise ValueError("zip_base64 decodes to an empty payload")
        return value


class IngestGitRequest(StrictModel):
    source_type: Literal["git_url"]
    git_url: str = Field(min_length=1, max_length=2048)


IngestRequest = Annotated[Union[IngestZipRequest, IngestGitRequest], Field(discriminator="source_type")]


class IngestResponse(StrictModel):
    task_id: str
    source_type: Literal["zip", "git_url"]
    tf_files: list[TfFileInfo]
    providers: list[ProviderInfo]
    required_version: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CheckRequest(StrictModel):
    task_id: str = Field(pattern=TASK_ID_PATTERN)
    checks: list[CheckType] = Field(min_length=1)

    @field_validator("checks")
    @classmethod
    def unique_checks(cls, value: list[CheckType]) -> list[CheckType]:
        if len(set(value)) != len(value):
            raise ValueError("checks must not contain duplicates")
        return value


class CheckResponse(StrictModel):
    task_id: str
    runs: list[CheckRun]


class CaptureRequest(StrictModel):
    task_id: str = Field(pattern=TASK_ID_PATTERN)


class CaptureResponse(StrictModel):
    available: bool
    reason: str | None = None
    plan_digest: str | None = None
    redacted_plan: dict | None = None
    captured_at: datetime | None = None
    truncated: bool = False


class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: str
    version: str


class ToolCapability(StrictModel):
    available: bool
    path: str | None = None
    version: str | None = None
    detail: str | None = None


class CheckCapability(StrictModel):
    binary: str
    requires: list[str]
    available: bool
    argv_preview: list[str]


class SandboxCapability(StrictModel):
    mode: str
    containerized: bool
    limitations: list[str]


class LimitsCapability(StrictModel):
    check_timeout_s: int
    ingest_timeout_s: int
    max_zip_bytes: int
    max_uncompressed_bytes: int
    max_zip_entries: int
    max_compression_ratio: int
    max_output_read_bytes: int


class CapabilitiesResponse(StrictModel):
    service: str
    version: str
    apply_enabled: bool
    tools: dict[str, ToolCapability]
    checks: dict[str, CheckCapability]
    sandbox: SandboxCapability
    limits: LimitsCapability
