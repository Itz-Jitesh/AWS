import pytest

from helpers import BASE_TF
from planproof_ai.config import AIConfig


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "main.tf").write_text(BASE_TF, encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def config() -> AIConfig:
    return AIConfig()
