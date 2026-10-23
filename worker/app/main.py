from __future__ import annotations

import base64
import io
import shutil
import zipfile
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from . import checks as check_pipeline
from .artifacts import load_plan, redacted_plan_view, store_plan
from .config import Settings, load_settings
from .contracts import ContractViolation
from .hcl_scan import scan
from .ingest import (
    GitCloneError,
    GitUnavailableError,
    UnsafeArchiveError,
    clone_repo,
    extract_archive,
    inspect_archive,
    validate_git_url,
)
from .models import (
    CapabilitiesResponse,
    CaptureRequest,
    CaptureResponse,
    CheckCapability,
    CheckRequest,
    CheckResponse,
    HealthResponse,
    IngestGitRequest,
    IngestRequest,
    IngestResponse,
    IngestZipRequest,
    LimitsCapability,
    SandboxCapability,
    ToolCapability,
)
from .redact import redact_text
from .sandbox import SandboxPolicyError, run_tool
from .store import TaskStore

SERVICE_NAME = "worker"
SERVICE_VERSION = "0.1.0"

SANDBOX_LIMITATIONS = [
    "subprocess isolation uses rlimits, timeouts, environment allowlisting, and workspace path confinement",
    "no kernel-level sandbox (container/VM/seccomp) is applied by this service itself",
    "deployments must run this service inside a disposable container or VM with cgroup and network limits",
    "network egress is not restricted by this service",
]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    resolved.ensure_dirs()
    app = FastAPI(title="PlanProof Worker", version=SERVICE_VERSION)
    app.state.settings = resolved
    app.state.store = TaskStore(resolved)
    app.state.version_cache: dict[str, str | None] = {}

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)

    @app.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities(request: Request) -> CapabilitiesResponse:
        settings = request.app.state.settings
        version_cache = request.app.state.version_cache
        terraform_path = shutil.which(settings.terraform_bin)
        git_path = shutil.which(settings.git_bin) if settings.git_enabled else None
        terraform_version = None
        if terraform_path:
            terraform_version = check_pipeline.probe_terraform_version(settings, version_cache)
        git_version = None
        if git_path:
            git_version = _probe_git_version(settings)
        tools = {
            "terraform": ToolCapability(
                available=terraform_path is not None,
                path=terraform_path,
                version=terraform_version,
                detail=None
                if terraform_path
                else f"executable '{settings.terraform_bin}' not found on PATH",
            ),
            "git": ToolCapability(
                available=git_path is not None,
                path=git_path,
                version=git_version,
                detail=None
                if git_path
                else (
                    "git ingestion disabled by configuration"
                    if not settings.git_enabled
                    else f"executable '{settings.git_bin}' not found on PATH"
                ),
            ),
        }
        check_caps = {
            name: CheckCapability(
                binary=settings.terraform_bin,
                requires=list(spec.requires),
                available=terraform_path is not None,
                argv_preview=[settings.terraform_bin, *spec.argv],
            )
            for name, spec in check_pipeline.CHECKS.items()
        }
        return CapabilitiesResponse(
            service=SERVICE_NAME,
            version=SERVICE_VERSION,
            apply_enabled=False,
            tools=tools,
            checks=check_caps,
            sandbox=SandboxCapability(
                mode="rlimit-subprocess",
                containerized=False,
                limitations=SANDBOX_LIMITATIONS,
            ),
            limits=LimitsCapability(
                check_timeout_s=settings.check_timeout_s,
                ingest_timeout_s=settings.ingest_timeout_s,
                max_zip_bytes=settings.max_zip_bytes,
                max_uncompressed_bytes=settings.max_uncompressed_bytes,
                max_zip_entries=settings.max_zip_entries,
                max_compression_ratio=settings.max_compression_ratio,
                max_output_read_bytes=settings.max_output_read_bytes,
            ),
        )

    @app.post("/ingest", response_model=IngestResponse)
    def ingest(payload: IngestRequest, request: Request) -> IngestResponse:
        settings = request.app.state.settings
        store: TaskStore = request.app.state.store
        if isinstance(payload, IngestZipRequest):
            try:
                zip_bytes = base64.b64decode(payload.zip_base64, validate=True)
            except Exception:
                raise HTTPException(status_code=422, detail="zip_base64 is not valid base64")
            if len(zip_bytes) > settings.max_zip_bytes:
                raise HTTPException(
                    status_code=413,
                    detail={"code": "PAYLOAD_TOO_LARGE", "message": "ZIP payload exceeds limit"},
                )
            return _ingest_zip(settings, store, zip_bytes, "zip")
        return _ingest_git(settings, store, payload.git_url)

    @app.post("/ingest/upload", response_model=IngestResponse)
    def ingest_upload(request: Request, file: UploadFile = File(...)) -> IngestResponse:
        settings = request.app.state.settings
        store: TaskStore = request.app.state.store
        data = file.file.read(settings.max_zip_bytes + 1)
        if len(data) > settings.max_zip_bytes:
            raise HTTPException(
                status_code=413,
                detail={"code": "PAYLOAD_TOO_LARGE", "message": "ZIP payload exceeds limit"},
            )
        if not data:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_ZIP", "message": "uploaded file is empty"},
            )
        return _ingest_zip(settings, store, data, "zip")

    @app.post("/check", response_model=CheckResponse)
    def check(payload: CheckRequest, request: Request) -> CheckResponse:
        settings = request.app.state.settings
        store: TaskStore = request.app.state.store
        paths = _get_task(store, payload.task_id)
        if not paths.repo.is_dir():
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_MISSING", "message": "workspace files are missing"},
            )
        try:
            runs = check_pipeline.run_checks(
                settings, paths, payload.checks, request.app.state.version_cache
            )
        except (SandboxPolicyError, ContractViolation) as exc:
            raise HTTPException(
                status_code=500,
                detail={"code": "INTERNAL_ERROR", "message": str(exc)},
            )
        return CheckResponse(task_id=payload.task_id, runs=runs)

    @app.post("/capture", response_model=CaptureResponse)
    def capture(payload: CaptureRequest, request: Request) -> CaptureResponse:
        settings = request.app.state.settings
        store: TaskStore = request.app.state.store
        paths = _get_task(store, payload.task_id)
        existing = load_plan(paths)
        if existing is not None:
            raw_plan, digest, captured_at = existing
            return CaptureResponse(
                available=True,
                plan_digest=digest,
                redacted_plan=redacted_plan_view(raw_plan),
                captured_at=captured_at,
                truncated=False,
            )
        plan_file = paths.repo / "tfplan"
        if not plan_file.is_file():
            return CaptureResponse(
                available=False,
                reason="no plan artifact available for this task; run the 'plan' check first",
            )
        if shutil.which(settings.terraform_bin) is None:
            return CaptureResponse(
                available=False,
                reason=(
                    f"terraform executable '{settings.terraform_bin}' not found; "
                    "plan JSON cannot be rendered"
                ),
            )
        stdout_path = paths.artifacts / "capture_show.stdout.raw"
        stderr_path = paths.artifacts / "capture_show.stderr.raw"
        result = run_tool(
            settings,
            [settings.terraform_bin, "show", "-json", "tfplan"],
            cwd=paths.repo,
            workspace=paths.root,
            timeout_s=settings.check_timeout_s,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            allowed_binaries={settings.terraform_bin},
        )
        raw_plan_text = ""
        if stdout_path.is_file():
            raw_plan_text = stdout_path.read_text(encoding="utf-8", errors="replace")
        for path in (stdout_path, stderr_path):
            if path.exists():
                path.unlink()
        if result.exit_code == 0 and raw_plan_text.strip():
            digest, captured_at = store_plan(paths, raw_plan_text)
            return CaptureResponse(
                available=True,
                plan_digest=digest,
                redacted_plan=redacted_plan_view(raw_plan_text),
                captured_at=captured_at,
                truncated=False,
            )
        reason = "plan JSON could not be rendered"
        if result.timed_out:
            reason = "plan JSON rendering timed out"
        elif result.killed_by_signal:
            reason = f"plan JSON rendering terminated by signal {result.signal_name}"
        elif result.spawn_error:
            reason = f"plan JSON rendering could not start: {result.spawn_error}"
        elif result.stderr_text.strip():
            reason = redact_text(result.stderr_text.strip().splitlines()[0])[:300]
        return CaptureResponse(available=False, reason=reason)

    return app


def _get_task(store: TaskStore, task_id: str):
    try:
        return store.get(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"code": "TASK_NOT_FOUND", "message": "unknown task_id"},
        )


def _ingest_zip(
    settings: Settings, store: TaskStore, zip_bytes: bytes, source_type: Literal["zip", "git_url"]
) -> IngestResponse:
    try:
        probe = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ZIP", "message": "payload is not a valid ZIP archive"},
        )
    with probe:
        try:
            inspect_archive(probe, settings)
        except UnsafeArchiveError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "UNSAFE_ARCHIVE", "message": exc.reason},
            )
    paths = store.create(with_repo_dir=True)
    try:
        extract_archive(zip_bytes, paths.repo, settings)
    except UnsafeArchiveError as exc:
        store.delete(paths.task_id)
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSAFE_ARCHIVE", "message": exc.reason},
        )
    return _scan_response(paths, source_type)


def _ingest_git(settings: Settings, store: TaskStore, git_url: str) -> IngestResponse:
    try:
        url = validate_git_url(git_url)
    except UnsafeArchiveError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSAFE_GIT_URL", "message": exc.reason},
        )
    paths = store.create(with_repo_dir=False)
    try:
        clone_repo(url, paths.repo, settings)
    except GitUnavailableError as exc:
        store.delete(paths.task_id)
        raise HTTPException(
            status_code=503,
            detail={"code": "GIT_UNAVAILABLE", "message": str(exc)},
        )
    except GitCloneError as exc:
        store.delete(paths.task_id)
        raise HTTPException(
            status_code=502,
            detail={"code": "CLONE_FAILED", "message": exc.detail},
        )
    return _scan_response(paths, "git_url")


def _scan_response(paths, source_type: Literal["zip", "git_url"]) -> IngestResponse:
    tf_files, providers, required_version = scan(paths.repo)
    warnings: list[str] = []
    if not tf_files:
        warnings.append("no Terraform .tf files were detected in the repository")
    return IngestResponse(
        task_id=paths.task_id,
        source_type=source_type,
        tf_files=tf_files,
        providers=providers,
        required_version=required_version,
        warnings=warnings,
    )


def _probe_git_version(settings: Settings) -> str | None:
    tmp_dir = settings.data_dir / "tmp"
    home_dir = settings.data_dir / "home"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    result = run_tool(
        settings,
        [settings.git_bin, "--version"],
        cwd=settings.data_dir,
        workspace=settings.data_dir,
        timeout_s=settings.version_probe_timeout_s,
        stdout_path=tmp_dir / "git_version.stdout.log",
        stderr_path=tmp_dir / "git_version.stderr.log",
        allowed_binaries={settings.git_bin},
    )
    if result.exit_code == 0 and result.stdout_text.strip():
        return result.stdout_text.strip().splitlines()[0].strip()
    return None


app = create_app()
