import os
from dataclasses import dataclass, field, replace

DEFAULT_SAGEMAKER_MODEL_ID = "google/gemma-4-E4B-it"
PAYLOAD_MODES = ("planproof", "hf", "openai")


@dataclass(frozen=True)
class PatchLimits:
    max_bytes: int = 65536
    max_files: int = 8
    max_changed_lines: int = 400
    allowed_suffixes: tuple[str, ...] = (".tf", ".tf.json")
    allow_resource_removal: bool = False


@dataclass(frozen=True)
class AIConfig:
    model_backend: str = "mock"
    model_id: str = "mock-llm-v1"
    model_mode: str = "merged"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_s: int = 300
    sagemaker_endpoint_name: str = ""
    sagemaker_region: str = ""
    sagemaker_payload_mode: str = "planproof"
    sagemaker_timeout_s: int = 120
    worker_base_url: str = ""
    audit_base_url: str = ""
    max_tokens: int = 2048
    max_repair_attempts: int = 3
    max_prompt_file_bytes: int = 8192
    max_prompt_workspace_files: int = 50
    max_diagnostics_chars: int = 6000
    patch: PatchLimits = field(default_factory=PatchLimits)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "AIConfig":
        env = os.environ if env is None else env

        def _int(name: str, default: int) -> int:
            raw = env.get(name, "")
            try:
                return int(raw) if raw else default
            except ValueError:
                return default

        backend = env.get("MODEL_BACKEND", "").strip()
        endpoint = env.get("SAGEMAKER_ENDPOINT_NAME", "").strip()
        if not backend:
            backend = "sagemaker" if endpoint else "mock"
        if env.get("MODEL_ID", "").strip():
            model_id = env["MODEL_ID"].strip()
        elif backend == "sagemaker":
            model_id = DEFAULT_SAGEMAKER_MODEL_ID
        elif backend == "ollama":
            model_id = env.get("OLLAMA_MODEL_ID", "gemma3")
        else:
            model_id = "mock-llm-v1"
        region = (
            env.get("SAGEMAKER_REGION", "").strip()
            or env.get("AWS_REGION", "").strip()
            or env.get("AWS_DEFAULT_REGION", "").strip()
        )
        payload_mode = env.get("SAGEMAKER_PAYLOAD_MODE", "planproof").strip().lower() or "planproof"
        return cls(
            model_backend=backend,
            model_id=model_id,
            model_mode=env.get("MODEL_MODE", "merged"),
            ollama_base_url=env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_timeout_s=_int("OLLAMA_TIMEOUT_S", 300),
            sagemaker_endpoint_name=endpoint,
            sagemaker_region=region,
            sagemaker_payload_mode=payload_mode,
            sagemaker_timeout_s=_int("SAGEMAKER_TIMEOUT_S", 120),
            worker_base_url=env.get("WORKER_BASE_URL", "").strip(),
            audit_base_url=env.get("AUDIT_BASE_URL", "").strip(),
            max_tokens=_int("LLM_MAX_TOKENS", 2048),
            max_repair_attempts=min(_int("MAX_REPAIR_ATTEMPTS", 3), 3),
        )

    @property
    def worker_mode(self) -> str:
        return "http" if self.worker_base_url else "mock"

    @property
    def audit_mode(self) -> str:
        return "http" if self.audit_base_url else "mock"

    def with_patch_limits(self, **kwargs) -> "AIConfig":
        return replace(self, patch=replace(self.patch, **kwargs))
