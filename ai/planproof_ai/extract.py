import json
import re

from .config import AIConfig
from .contracts import Requirement, RequirementStatus
from .errors import LLMResponseError
from .llm.base import LLMAdapter, LLMRequest
from .redaction import redact

_FENCE_RE = re.compile(r"```(?:json)?\n(.*?)```", re.DOTALL)


def _parse_requirements_payload(text: str) -> list[dict] | None:
    if not text:
        return None
    candidates: list[str] = []
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    stripped = text.strip()
    candidates.append(stripped)
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("requirements"), list):
            return [item for item in data["requirements"] if isinstance(item, dict)]
    return None


def build_requirements_prompt(goal: str) -> str:
    return (
        "Extract engineering requirements from the user's Terraform goal.\n"
        "Return ONLY a JSON array; no prose. Each element must be:\n"
        '{"text": "<testable requirement>", "mandatory": true|false, '
        '"verification": "<how a reviewer would verify it>"}\n'
        "Requirements must be explicit and testable where possible.\n"
        "Do not assign a status; requirements start unverified.\n\n"
        f"Goal:\n{goal.strip()}"
    )


def _normalize(items: list[dict]) -> list[Requirement]:
    requirements: list[Requirement] = []
    for idx, item in enumerate(items, start=1):
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        mandatory = item.get("mandatory")
        verification = item.get("verification")
        notes = verification if isinstance(verification, str) and verification.strip() else None
        requirements.append(
            Requirement(
                requirement_id=f"req-{idx}",
                text=text.strip(),
                mandatory=bool(mandatory) if isinstance(mandatory, bool) else True,
                status=RequirementStatus.UNVERIFIED,
                evidence=[],
                notes=redact(notes) if notes else None,
            )
        )
    return requirements


def extract_requirements(
    goal: str,
    *,
    llm: LLMAdapter,
    config: AIConfig | None = None,
) -> list[Requirement]:
    config = config or AIConfig()
    cleaned = (goal or "").strip()
    if not cleaned:
        raise ValueError("goal must not be empty")
    request = LLMRequest(
        prompt=build_requirements_prompt(cleaned),
        diagnostics="",
        max_tokens=config.max_tokens,
    )
    response = llm.complete(request)
    items = _parse_requirements_payload(response.rationale)
    requirements = _normalize(items or [])
    if not requirements:
        requirements = [
            Requirement(
                requirement_id="req-1",
                text=cleaned,
                mandatory=True,
                status=RequirementStatus.UNVERIFIED,
                evidence=[],
                notes="derived from goal; model output was not usable",
            )
        ]
    for req in requirements:
        req.status = RequirementStatus.UNVERIFIED
        req.evidence = []
    return requirements
