from enum import Enum

from pydantic import BaseModel, Field

from .config import AIConfig
from .contracts import CheckRun, CheckStatus, Patch, PlanSummary, Requirement, RequirementStatus
from .errors import (
    LLMResponseError,
    LLMUnavailableError,
    PatchValidationError,
)
from .extract import extract_requirements
from .generate import generate_patch
from .llm.base import LLMAdapter
from .patching import apply_patch
from .redaction import redact


class StopReason(str, Enum):
    RESOLVED = "resolved"
    REQUIREMENTS_NOT_MET = "requirements_not_met"
    UNSAFE_PATCH = "unsafe_patch"
    REGRESSION = "regression"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    WORKER_FAILURE = "worker_failure"
    AUDIT_FAILURE = "audit_failure"
    LLM_FAILURE = "llm_failure"
    INTENT_VIOLATED = "intent_violated"


class Attempt(BaseModel):
    attempt_number: int
    patch: Patch | None = None
    applied: bool = False
    checks_after: list[CheckRun] = Field(default_factory=list)
    note: str = ""


class RepairResult(BaseModel):
    task_id: str
    workspace: str
    stop_reason: StopReason
    success: bool
    attempts: list[Attempt] = Field(default_factory=list)
    checks: list[CheckRun] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    applied_diff: str = ""
    note: str = ""


def suite_passed(checks: list[CheckRun]) -> bool:
    return bool(checks) and all(c.status == CheckStatus.PASSED for c in checks)


def is_regression(previous: list[CheckRun], current: list[CheckRun]) -> bool:
    by_id = {c.check_id: c for c in current}
    for check in previous:
        if check.status != CheckStatus.PASSED:
            continue
        after = by_id.get(check.check_id)
        if after is None or after.status != CheckStatus.PASSED:
            return True
    return False


def build_diagnostics(
    checks: list[CheckRun],
    requirements: list[Requirement],
    applied_diff: str,
    config: AIConfig,
) -> str:
    lines: list[str] = ["Check suite status (redacted):"]
    for check in checks:
        exit_part = f" exit_code={check.exit_code}" if check.exit_code is not None else ""
        lines.append(
            f"- {check.check_id} [{check.tool}] {check.status.value}: {check.summary}{exit_part}"
        )
        for limitation in check.limitations:
            lines.append(f"  limitation: {limitation}")
    lines.append("Requirements:")
    for req in requirements:
        flag = "mandatory" if req.mandatory else "optional"
        lines.append(f"- ({flag}) [{req.status.value}] {req.text}")
        if req.evidence:
            lines.append(f"  evidence: {'; '.join(req.evidence)}")
    if applied_diff:
        lines.append("Diff applied so far (tail, may be truncated):")
        lines.append(applied_diff)
    text = redact("\n".join(lines))
    if len(text) > config.max_diagnostics_chars:
        text = text[: config.max_diagnostics_chars]
    return text


def repair_loop(
    task_id: str,
    workspace: str,
    *,
    llm: LLMAdapter,
    worker,
    audit,
    goal: str | None = None,
    requirements: list[Requirement] | None = None,
    max_attempts: int = 3,
    config: AIConfig | None = None,
) -> RepairResult:
    config = config or AIConfig()
    cap = max(1, min(int(max_attempts), config.max_repair_attempts, 3))

    if requirements is None:
        if not goal:
            raise ValueError("either requirements or goal must be provided")
        requirements = extract_requirements(goal, llm=llm, config=config)

    def stop(
        reason: StopReason,
        checks: list[CheckRun],
        reqs: list[Requirement],
        applied_diff: str,
        attempts: list[Attempt],
        note: str = "",
        success: bool | None = None,
    ) -> RepairResult:
        return RepairResult(
            task_id=task_id,
            workspace=workspace,
            stop_reason=reason,
            success=success if success is not None else reason == StopReason.RESOLVED,
            attempts=attempts,
            checks=checks,
            requirements=reqs,
            applied_diff=applied_diff,
            note=redact(note),
        )

    def capture_plan() -> PlanSummary | None:
        try:
            plan_json = worker.capture_plan_json(workspace, task_id)
            if not plan_json:
                return None
            return audit.classify_plan(workspace, plan_json)
        except Exception:
            return None

    attempts: list[Attempt] = []
    applied_parts: list[str] = []
    plan_summary = capture_plan()

    try:
        current = worker.run_check_suite(workspace, task_id)
    except Exception as exc:
        return stop(
            StopReason.WORKER_FAILURE, [], requirements, "", attempts,
            note=f"baseline check suite failed: {exc}",
        )

    while True:
        suite_ok = suite_passed(current)
        joined_diff = "".join(part + "\n" for part in applied_parts)

        if suite_ok:
            try:
                requirements = audit.check_intent(requirements, joined_diff, plan_summary)
            except Exception as exc:
                return stop(
                    StopReason.AUDIT_FAILURE, current, requirements, joined_diff, attempts,
                    note=f"intent check failed: {exc}",
                )
            violated = [
                r for r in requirements
                if r.mandatory and r.status == RequirementStatus.VIOLATED
            ]
            if violated:
                return stop(
                    StopReason.INTENT_VIOLATED, current, requirements, joined_diff, attempts,
                    note=f"mandatory requirement violated: {violated[0].text}",
                )
            mandatory = [r for r in requirements if r.mandatory]
            if all(r.status == RequirementStatus.SATISFIED for r in mandatory):
                return stop(
                    StopReason.RESOLVED, current, requirements, joined_diff, attempts,
                    success=True,
                )

        if len(attempts) >= cap:
            reason = (
                StopReason.REQUIREMENTS_NOT_MET if suite_ok else StopReason.ATTEMPTS_EXHAUSTED
            )
            return stop(reason, current, requirements, joined_diff, attempts,
                        note="repair budget exhausted")

        diagnostics = build_diagnostics(current, requirements, joined_diff, config)
        try:
            patch = generate_patch(workspace, requirements, diagnostics, llm=llm, config=config)
        except PatchValidationError as exc:
            attempts.append(
                Attempt(attempt_number=len(attempts) + 1, applied=False, note=str(exc))
            )
            return stop(
                StopReason.UNSAFE_PATCH, current, requirements, joined_diff, attempts,
                note=f"rejected patch: {exc}",
            )
        except (LLMUnavailableError, LLMResponseError) as exc:
            return stop(
                StopReason.LLM_FAILURE, current, requirements, joined_diff, attempts,
                note=f"model call failed: {exc}",
            )

        try:
            apply_patch(workspace, patch, config.patch)
        except PatchValidationError as exc:
            attempts.append(
                Attempt(
                    attempt_number=len(attempts) + 1, patch=patch, applied=False, note=str(exc)
                )
            )
            return stop(
                StopReason.UNSAFE_PATCH, current, requirements, joined_diff, attempts,
                note=f"rejected patch application: {exc}",
            )

        applied_parts.append(patch.unified_diff.strip())
        try:
            after = worker.run_check_suite(workspace, task_id)
        except Exception as exc:
            attempts.append(
                Attempt(
                    attempt_number=len(attempts) + 1, patch=patch, applied=True,
                    note=f"re-check failed: {exc}",
                )
            )
            return stop(
                StopReason.WORKER_FAILURE, current, requirements, joined_diff, attempts,
                note=f"re-run of check suite failed: {exc}",
            )

        attempts.append(
            Attempt(
                attempt_number=len(attempts) + 1, patch=patch, applied=True,
                checks_after=after, note="patch applied and suite re-run",
            )
        )
        if is_regression(current, after):
            return stop(
                StopReason.REGRESSION, after, requirements, joined_diff, attempts,
                note="a previously passing check regressed after the patch",
            )
        current = after
