from typing import Protocol, runtime_checkable

import httpx

from .contracts import CheckRun, PlanSummary, Requirement
from .errors import AuditError, WorkerUnavailableError


@runtime_checkable
class WorkerClient(Protocol):
    def run_check_suite(self, workspace: str, task_id: str) -> list[CheckRun]: ...

    def capture_plan_json(self, workspace: str, task_id: str) -> dict | None: ...


@runtime_checkable
class AuditClient(Protocol):
    def check_intent(
        self,
        requirements: list[Requirement],
        diff: str,
        plan_summary: PlanSummary | None,
    ) -> list[Requirement]: ...

    def classify_plan(self, workspace: str, plan_json: dict) -> PlanSummary: ...


class HttpWorkerClient:
    def __init__(self, base_url: str, timeout: float = 300.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    def run_check_suite(self, workspace: str, task_id: str) -> list[CheckRun]:
        return self._post("/check", workspace, task_id, "checks", CheckRun)

    def capture_plan_json(self, workspace: str, task_id: str) -> dict | None:
        return self._post("/capture", workspace, task_id, "plan_json", None)

    def _post(self, path: str, workspace: str, task_id: str, key: str, item_model):
        payload = {"workspace": workspace, "task_id": task_id}
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise WorkerUnavailableError(f"worker unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise WorkerUnavailableError(
                f"worker {path} returned HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise WorkerUnavailableError(f"worker {path} returned non-JSON body") from exc
        if not isinstance(data, dict) or key not in data:
            raise WorkerUnavailableError(f"worker {path} response missing '{key}'")
        value = data[key]
        if item_model is None:
            return value if isinstance(value, dict) else None
        if not isinstance(value, list):
            raise WorkerUnavailableError(f"worker {path} field '{key}' must be a list")
        try:
            return [item_model.model_validate(item) for item in value]
        except ValueError as exc:
            raise WorkerUnavailableError(f"worker {path} returned invalid CheckRun: {exc}") from exc

    def close(self) -> None:
        self._client.close()


class HttpAuditClient:
    def __init__(self, base_url: str, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    def check_intent(
        self,
        requirements: list[Requirement],
        diff: str,
        plan_summary: PlanSummary | None,
    ) -> list[Requirement]:
        payload = {
            "requirements": [r.model_dump(mode="json") for r in requirements],
            "diff": diff,
            "plan_summary": plan_summary.model_dump(mode="json") if plan_summary else None,
        }
        data = self._request("/intent", payload)
        items = data.get("requirements")
        if not isinstance(items, list):
            raise AuditError("audit /intent response missing 'requirements'")
        try:
            return [Requirement.model_validate(item) for item in items]
        except ValueError as exc:
            raise AuditError(f"audit returned invalid Requirement: {exc}") from exc

    def classify_plan(self, workspace: str, plan_json: dict) -> PlanSummary:
        data = self._request("/plan/classify", {"workspace": workspace, "plan_json": plan_json})
        try:
            return PlanSummary.model_validate(data.get("plan_summary", data))
        except ValueError as exc:
            raise AuditError(f"audit returned invalid PlanSummary: {exc}") from exc

    def _request(self, path: str, payload: dict) -> dict:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise AuditError(f"audit unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise AuditError(f"audit {path} returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise AuditError(f"audit {path} returned non-JSON body") from exc
        if not isinstance(data, dict):
            raise AuditError(f"audit {path} returned non-object JSON")
        return data

    def close(self) -> None:
        self._client.close()
