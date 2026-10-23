from fastapi import FastAPI, Path
from pydantic import BaseModel, ConfigDict, Field

from .clients import AuditClient, HttpAuditClient, HttpWorkerClient, WorkerClient
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
from .llm.factory import create_adapter, resolve_backend
from .llm.ollama import OllamaAdapter
from .llm.sagemaker import SageMakerAdapter
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


class ModelCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    adapter: str
    model_id: str
    model_mode: str
    payload_mode: str | None = None
    endpoint_name: str | None = None
    endpoint_configured: bool
    requires_live_endpoint: bool


class ServiceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    base_url: str | None = None


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    model: ModelCapability
    worker: ServiceCapability
    audit: ServiceCapability
    repair_max_attempts: int


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
    worker = worker or (
        HttpWorkerClient(config.worker_base_url)
        if config.worker_base_url
        else MockWorkerClient()
    )
    audit = audit or (
        HttpAuditClient(config.audit_base_url)
        if config.audit_base_url
        else MockAuditClient()
    )

    app = FastAPI(title="PlanProof AI Service (Agent C)", version="0.1.0")
    app.state.llm = llm
    app.state.worker = worker
    app.state.audit = audit
    app.state.config = config

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", model_backend=resolve_backend(config), model_id=llm.model_id
        )

    @app.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities() -> CapabilitiesResponse:
        backend = resolve_backend(config)
        live = backend != "mock"
        if isinstance(llm, SageMakerAdapter):
            endpoint_name = llm.endpoint_name or None
            endpoint_configured = llm.endpoint_configured
            payload_mode: str | None = llm.payload_mode
        elif isinstance(llm, OllamaAdapter):
            endpoint_name = llm.base_url
            endpoint_configured = True
            payload_mode = None
        else:
            endpoint_name = None
            endpoint_configured = False
            payload_mode = None
        return CapabilitiesResponse(
            status="ok",
            model=ModelCapability(
                backend=backend,
                adapter=type(llm).__name__,
                model_id=llm.model_id,
                model_mode=config.model_mode,
                payload_mode=payload_mode,
                endpoint_name=endpoint_name,
                endpoint_configured=endpoint_configured,
                requires_live_endpoint=live,
            ),
            worker=ServiceCapability(
                mode="http" if isinstance(worker, HttpWorkerClient) else "mock",
                base_url=config.worker_base_url or None,
            ),
            audit=ServiceCapability(
                mode="http" if isinstance(audit, HttpAuditClient) else "mock",
                base_url=config.audit_base_url or None,
            ),
            repair_max_attempts=config.max_repair_attempts,
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
        except LLMUnavailableError as exc:
            raise _http(503, exc) from exc
        except LLMResponseError as exc:
            raise _http(502, exc) from exc
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
