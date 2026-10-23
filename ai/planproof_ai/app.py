from fastapi import FastAPI, Path
from pydantic import BaseModel, ConfigDict, Field

from .clients import AuditClient, WorkerClient
from .config import AIConfig
from .contracts import Patch, Requirement
from .errors import (
    AuditError,
    LLMResponseError,
    LLMUnavailableError,
    PatchValidationError,
    WorkerUnavailableError,
)
from .extract import extract_requirements
from .generate import generate_patch
from .llm.base import LLMAdapter
from .llm.factory import create_adapter
from .repair import RepairResult, repair_loop
from .testing import MockAuditClient, MockWorkerClient


class RequirementsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)


class RequirementsResponse(BaseModel):
    requirements: list[Requirement]


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(min_length=1)
    goal: str | None = None
    requirements: list[Requirement] | None = None
    diagnostics: str = ""


class PatchResponse(BaseModel):
    patch: Patch


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(min_length=1)
    goal: str | None = None
    requirements: list[Requirement] | None = None
    max_attempts: int = Field(default=3, ge=1, le=3)


class RepairResponse(BaseModel):
    result: RepairResult


class HealthResponse(BaseModel):
    status: str
    model_backend: str
    model_id: str


def _resolve_requirements(
    goal: str | None, requirements: list[Requirement] | None, llm: LLMAdapter, config: AIConfig
) -> list[Requirement]:
    if requirements:
        return requirements
    if not goal:
        raise ValueError("either requirements or goal must be provided")
    return extract_requirements(goal, llm=llm, config=config)


def create_app(
    *,
    llm: LLMAdapter | None = None,
    worker: WorkerClient | None = None,
    audit: AuditClient | None = None,
    config: AIConfig | None = None,
) -> FastAPI:
    config = config or AIConfig.from_env()
    llm = llm or create_adapter(config)
    worker = worker or MockWorkerClient()
    audit = audit or MockAuditClient()

    app = FastAPI(title="PlanProof AI Service (Agent C)", version="0.1.0")
    app.state.llm = llm
    app.state.worker = worker
    app.state.audit = audit
    app.state.config = config

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", model_backend=config.model_backend, model_id=llm.model_id
        )

    @app.post(
        "/tasks/{task_id}/requirements",
        response_model=RequirementsResponse,
        response_model_exclude_none=True,
    )
    def requirements_endpoint(
        body: RequirementsRequest, task_id: str = Path(..., min_length=1)
    ) -> RequirementsResponse:
        try:
            reqs = extract_requirements(body.goal, llm=llm, config=config)
        except LLMUnavailableError as exc:
            raise _http(503, exc) from exc
        except LLMResponseError as exc:
            raise _http(502, exc) from exc
        return RequirementsResponse(requirements=reqs)

    @app.post(
        "/tasks/{task_id}/patch",
        response_model=PatchResponse,
        response_model_exclude_none=True,
    )
    def patch_endpoint(body: PatchRequest, task_id: str = Path(..., min_length=1)) -> PatchResponse:
        try:
            reqs = _resolve_requirements(body.goal, body.requirements, llm, config)
            patch = generate_patch(
                body.workspace, reqs, body.diagnostics, llm=llm, config=config
            )
        except ValueError as exc:
            raise _http(400, exc, code="bad_request") from exc
        except PatchValidationError as exc:
            raise _http(422, exc) from exc
        except (LLMUnavailableError, LLMResponseError) as exc:
            raise _http(503, exc) from exc
        return PatchResponse(patch=patch)

    @app.post(
        "/tasks/{task_id}/repair",
        response_model=RepairResponse,
        response_model_exclude_none=True,
    )
    def repair_endpoint(body: RepairRequest, task_id: str = Path(..., min_length=1)) -> RepairResponse:
        try:
            result = repair_loop(
                task_id,
                body.workspace,
                llm=llm,
                worker=worker,
                audit=audit,
                goal=body.goal,
                requirements=body.requirements,
                max_attempts=body.max_attempts,
                config=config,
            )
        except ValueError as exc:
            raise _http(400, exc, code="bad_request") from exc
        except LLMUnavailableError as exc:
            raise _http(503, exc) from exc
        except WorkerUnavailableError as exc:
            raise _http(503, exc) from exc
        except AuditError as exc:
            raise _http(503, exc) from exc
        return RepairResponse(result=result)

    return app


def _http(status: int, exc: Exception, code: str | None = None):
    from fastapi import HTTPException

    return HTTPException(
        status_code=status,
        detail={"code": code or getattr(exc, "code", "error"), "message": str(exc)},
    )


app = create_app()
