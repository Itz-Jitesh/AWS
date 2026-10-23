from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class TaskPaths:
    task_id: str
    root: Path
    repo: Path
    artifacts: Path
    home: Path
    tmp: Path


class TaskStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()

    def _paths_for(self, task_id: str) -> TaskPaths:
        if not TASK_ID_RE.fullmatch(task_id):
            raise KeyError(task_id)
        root = self.settings.data_dir / task_id
        return TaskPaths(
            task_id=task_id,
            root=root,
            repo=root / "repo",
            artifacts=root / "artifacts",
            home=root / "home",
            tmp=root / "tmp",
        )

    def create(self, with_repo_dir: bool = True) -> TaskPaths:
        task_id = uuid.uuid4().hex
        paths = self._paths_for(task_id)
        paths.root.mkdir(parents=True, exist_ok=False)
        os.chmod(paths.root, 0o700)
        paths.artifacts.mkdir()
        os.chmod(paths.artifacts, 0o700)
        paths.home.mkdir()
        os.chmod(paths.home, 0o700)
        paths.tmp.mkdir()
        os.chmod(paths.tmp, 0o700)
        if with_repo_dir:
            paths.repo.mkdir()
            os.chmod(paths.repo, 0o700)
        return paths

    def get(self, task_id: str) -> TaskPaths:
        paths = self._paths_for(task_id)
        if not paths.root.is_dir():
            raise KeyError(task_id)
        return paths

    def delete(self, task_id: str) -> None:
        try:
            paths = self._paths_for(task_id)
        except KeyError:
            return
        if paths.root.is_dir():
            shutil.rmtree(paths.root, ignore_errors=True)
