"""Live SageMaker integration test against a REAL endpoint.

CLASSIFICATION: LIVE. Nothing here is mocked. These tests are SKIPPED by
default and never count as passed unless explicitly enabled with:

    PLANPROOF_RUN_LIVE=1
    SAGEMAKER_ENDPOINT_NAME=<deployed endpoint>
    AWS credentials configured (aws configure / env vars)

If the endpoint or credentials are unavailable, the test is reported as
SKIPPED/BLOCKED — not passed. See ai/SAGEMAKER_INTEGRATION_TEST_RESULTS.md.
"""

import os

import pytest

from planproof_ai.config import AIConfig
from planproof_ai.llm.base import LLMRequest
from planproof_ai.llm.factory import create_adapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("PLANPROOF_RUN_LIVE") != "1"
        or not os.environ.get("SAGEMAKER_ENDPOINT_NAME"),
        reason=(
            "BLOCKED: live endpoint test disabled. Requires PLANPROOF_RUN_LIVE=1, "
            "SAGEMAKER_ENDPOINT_NAME, and AWS credentials. No endpoint has been "
            "deployed or authorized in this environment."
        ),
    ),
]


def _adapter():
    config = AIConfig.from_env()
    return create_adapter(config)


def test_live_planproof_envelope_round_trip():
    adapter = _adapter()
    response = adapter.complete(
        LLMRequest(
            prompt="Reply with a single short sentence confirming you are online.",
            diagnostics="",
            max_tokens=64,
        )
    )
    assert response.rationale.strip(), "endpoint returned an empty rationale"
    assert response.model_id
    assert response.finish_reason


def test_live_capabilities_endpoint_configured():
    adapter = _adapter()
    assert adapter.endpoint_configured is True
    assert adapter.payload_mode in ("planproof", "hf", "openai")
