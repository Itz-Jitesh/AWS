from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "workspace-data"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    terraform_bin: str = "terraform"
    git_bin: str = "git"
    check_timeout_s: int = 300
    ingest_timeout_s: int = 120
    version_probe_timeout_s: int = 10
    max_zip_bytes: int = 50 * 1024 * 1024
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    max_zip_entries: int = 10000
    max_compression_ratio: int = 200
    max_output_read_bytes: int = 1_000_000
    max_output_file_bytes: int = 32 * 1024 * 1024
    git_enabled: bool = True

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)


def load_settings() -> Settings:
    raw_dir = os.environ.get("WORKER_DATA_DIR")
    data_dir = Path(raw_dir).expanduser() if raw_dir else DEFAULT_DATA_DIR
    return Settings(
        data_dir=data_dir.resolve(),
        terraform_bin=os.environ.get("WORKER_TERRAFORM_BIN", "terraform"),
        git_bin=os.environ.get("WORKER_GIT_BIN", "git"),
        check_timeout_s=_env_int("WORKER_CHECK_TIMEOUT_S", 300),
        ingest_timeout_s=_env_int("WORKER_INGEST_TIMEOUT_S", 120),
        version_probe_timeout_s=_env_int("WORKER_VERSION_PROBE_TIMEOUT_S", 10),
        max_zip_bytes=_env_int("WORKER_MAX_ZIP_BYTES", 50 * 1024 * 1024),
        max_uncompressed_bytes=_env_int("WORKER_MAX_UNCOMPRESSED_BYTES", 200 * 1024 * 1024),
        max_zip_entries=_env_int("WORKER_MAX_ZIP_ENTRIES", 10000),
        max_compression_ratio=_env_int("WORKER_MAX_COMPRESSION_RATIO", 200),
        max_output_read_bytes=_env_int("WORKER_MAX_OUTPUT_READ_BYTES", 1_000_000),
        max_output_file_bytes=_env_int("WORKER_MAX_OUTPUT_FILE_BYTES", 32 * 1024 * 1024),
        git_enabled=_env_bool("WORKER_GIT_ENABLED", True),
    )
