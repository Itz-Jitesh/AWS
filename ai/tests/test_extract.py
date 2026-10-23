import pytest

from helpers import json_requirements_response, rationale_response
from planproof_ai.contracts import RequirementStatus
from planproof_ai.errors import LLMResponseError
from planproof_ai.extract import extract_requirements
from planproof_ai.llm.mock import MockLLMAdapter


def test_extract_parses_json_array():
    llm = MockLLMAdapter([
        json_requirements_response([
            {"text": "bucket must be private", "mandatory": True, "verification": "check public access block"},
            {"text": "tag environment", "mandatory": False},
        ])
    ])
    reqs = extract_requirements("Make the bucket private", llm=llm)
    assert [r.requirement_id for r in reqs] == ["req-1", "req-2"]
    assert reqs[0].mandatory is True
    assert reqs[0].notes == "check public access block"
    assert reqs[1].mandatory is False
    assert len(llm.requests) == 1


def test_extract_never_trusts_model_status():
    llm = MockLLMAdapter([
        json_requirements_response([
            {"text": "bucket private", "mandatory": True, "status": "Satisfied", "evidence": ["model says so"]}
        ])
    ])
    reqs = extract_requirements("goal", llm=llm)
    assert reqs[0].status == RequirementStatus.UNVERIFIED
    assert reqs[0].evidence == []


def test_extract_fenced_json():
    llm = MockLLMAdapter([rationale_response('```json\n[{"text": "keep bucket", "mandatory": true}]\n```')])
    reqs = extract_requirements("keep bucket", llm=llm)
    assert reqs[0].text == "keep bucket"
    assert reqs[0].status == RequirementStatus.UNVERIFIED


def test_extract_fallback_on_garbage_output():
    llm = MockLLMAdapter([rationale_response("I cannot parse the goal, sorry.")])
    reqs = extract_requirements("Make the bucket private", llm=llm)
    assert len(reqs) == 1
    assert reqs[0].text == "Make the bucket private"
    assert reqs[0].mandatory is True
    assert reqs[0].status == RequirementStatus.UNVERIFIED


def test_extract_drops_empty_text_items():
    llm = MockLLMAdapter([
        json_requirements_response([
            {"text": "   ", "mandatory": True},
            {"text": "real requirement", "mandatory": True},
        ])
    ])
    reqs = extract_requirements("goal", llm=llm)
    assert len(reqs) == 1
    assert reqs[0].text == "real requirement"


def test_extract_rejects_empty_goal():
    with pytest.raises(ValueError):
        extract_requirements("   ", llm=MockLLMAdapter([]))


def test_extract_propagates_llm_failure():
    llm = MockLLMAdapter([])
    with pytest.raises(LLMResponseError):
        extract_requirements("goal", llm=llm)
