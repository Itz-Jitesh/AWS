import json

from planproof_ai.llm.base import LLMResponse

BASE_TF = """resource "aws_s3_bucket" "b" {
  bucket = "demo"
}
"""

BASE_LINES = BASE_TF.splitlines()


def tf_response(patch: str | None, rationale: str = "minimal safe fix") -> LLMResponse:
    return LLMResponse(patch=patch, rationale=rationale, model_id="mock-llm-v1")


def rationale_response(text: str) -> LLMResponse:
    return LLMResponse(patch=None, rationale=text, model_id="mock-llm-v1")


def json_requirements_response(items: list[dict]) -> LLMResponse:
    return rationale_response(json.dumps(items))


def unified_replace(rel: str, old_lines: list[str], idx: int, old_line: str, new_line: str) -> str:
    count = len(old_lines)
    parts = [f"--- a/{rel}", f"+++ b/{rel}", f"@@ -1,{count} +1,{count} @@"]
    for i, line in enumerate(old_lines):
        if i == idx:
            parts.append(f"-{old_line}")
            parts.append(f"+{new_line}")
        else:
            parts.append(f" {line}")
    return "\n".join(parts) + "\n"


def unified_append(rel: str, old_lines: list[str], marker: str) -> str:
    count = len(old_lines)
    parts = [f"--- a/{rel}", f"+++ b/{rel}", f"@@ -1,{count} +1,{count + 1} @@"]
    parts.extend(f" {line}" for line in old_lines)
    parts.append(f"+{marker}")
    return "\n".join(parts) + "\n"


def secret_check() -> dict:
    return {
        "summary": "failed: password=hunter2 key AKIA1234567890ABCDEF",
        "exit_code": 1,
    }
