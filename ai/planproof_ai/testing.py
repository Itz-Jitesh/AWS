from datetime import datetime, timezone

from .contracts import (
    CheckRun,
    CheckStatus,
    PlanSummary,
    Requirement,
    RequirementStatus,
)


def make_check(
    check_id: str,
    status: CheckStatus | str,
    tool: str = "terraform",
    summary: str = "",
    exit_code: int | None = None,
    limitations: list[str] | None = None,
) -> CheckRun:
    if isinstance(status, str):
        status = CheckStatus(status)
    return CheckRun(
        check_id=check_id,
        tool=tool,
        status=status,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        duration_ms=10,
        summary=summary or status.value,
        exit_code=exit_code,
        limitations=limitations or [],
    )


def make_requirement(
    text: str,
    requirement_id: str = "req-1",
    mandatory: bool = True,
    status: RequirementStatus | str = RequirementStatus.UNVERIFIED,
    evidence: list[str] | None = None,
) -> Requirement:
    if isinstance(status, str):
        status = RequirementStatus(status)
    return Requirement(
        requirement_id=requirement_id,
        text=text,
        mandatory=mandatory,
        status=status,
        evidence=evidence or [],
    )


def make_plan_summary(digest: str = "a" * 64, destroy: int = 0) -> PlanSummary:
    return PlanSummary(
        plan_digest=digest,
        create=0,
        update=0,
        replace=0,
        destroy=destroy,
        destructive_actions=[],
        has_changes=bool(destroy),
    )


class MockWorkerClient:
    def __init__(
        self,
        suites: list[list[CheckRun]] | None = None,
        exceptions: list[Exception | None] | None = None,
        plan_json: dict | None = None,
    ):
        self._suites = [list(s) for s in (suites or [])]
        self._exceptions = list(exceptions or [])
        self.plan_json = plan_json
        self.check_calls: list[tuple[str, str]] = []
        self.capture_calls: list[tuple[str, str]] = []

    def run_check_suite(self, workspace: str, task_id: str) -> list[CheckRun]:
        self.check_calls.append((workspace, task_id))
        call_index = len(self.check_calls) - 1
        if call_index < len(self._exceptions) and self._exceptions[call_index] is not None:
            raise self._exceptions[call_index]
        if not self._suites:
            return []
        suite = self._suites.pop(0) if len(self._suites) > 1 else self._suites[0]
        return [check.model_copy(deep=True) for check in suite]

    def capture_plan_json(self, workspace: str, task_id: str) -> dict | None:
        self.capture_calls.append((workspace, task_id))
        return self.plan_json


class MockAuditClient:
    def __init__(
        self,
        intent_queue: list[list[Requirement]] | None = None,
        intent_fn=None,
        plan_summary: PlanSummary | None = None,
    ):
        self._intent_queue = [list(items) for items in (intent_queue or [])]
        self._intent_fn = intent_fn
        self.plan_summary = plan_summary or make_plan_summary()
        self.intent_calls: list[tuple[list[Requirement], str, PlanSummary | None]] = []
        self.classify_calls: list[tuple[str, dict]] = []

    def check_intent(
        self,
        requirements: list[Requirement],
        diff: str,
        plan_summary: PlanSummary | None,
    ) -> list[Requirement]:
        self.intent_calls.append(
            ([r.model_copy(deep=True) for r in requirements], diff, plan_summary)
        )
        if self._intent_fn is not None:
            return self._intent_fn(requirements, diff, plan_summary)
        if self._intent_queue:
            items = self._intent_queue.pop(0) if len(self._intent_queue) > 1 else self._intent_queue[0]
            return [item.model_copy(deep=True) for item in items]
        return [r.model_copy(deep=True) for r in requirements]

    def classify_plan(self, workspace: str, plan_json: dict) -> PlanSummary:
        self.classify_calls.append((workspace, plan_json))
        return self.plan_summary
