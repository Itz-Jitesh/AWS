import os
from dataclasses import dataclass, field, replace


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
    sagemaker_endpoint_name: str = ""
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

        return cls(
            model_backend=env.get("MODEL_BACKEND", "mock"),
            model_id=env.get("MODEL_ID", "mock-llm-v1"),
            model_mode=env.get("MODEL_MODE", "merged"),
            ollama_base_url=env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            sagemaker_endpoint_name=env.get("SAGEMAKER_ENDPOINT_NAME", ""),
            max_tokens=_int("LLM_MAX_TOKENS", 2048),
            max_repair_attempts=min(_int("MAX_REPAIR_ATTEMPTS", 3), 3),
        )

    def with_patch_limits(self, **kwargs) -> "AIConfig":
        return replace(self, patch=replace(self.patch, **kwargs))
