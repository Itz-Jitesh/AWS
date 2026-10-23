"""Guards for the paid-resource deploy script.

These tests verify ONLY the refusal/authorization paths. No AWS call is ever
made: `_client` is stubbed to fail the test if a boto3 client would be
constructed, and the script must exit with code 2 before that happens.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "deploy_endpoint.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("planproof_deploy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["planproof_deploy"] = module
    spec.loader.exec_module(module)
    return module


deploy_mod = _load_module()

ROLE = "--role-arn"
ROLE_VALUE = "arn:aws:iam::123456789012:role/PlanProofSageMaker"


def _no_aws_client(region):
    pytest.fail("AWS client must not be constructed before authorization")


def test_script_lives_outside_pytest_collection():
    assert SCRIPT.exists()
    assert SCRIPT.parent.name == "deploy"
    assert not (SCRIPT.parent.parent / "tests" / SCRIPT.name).exists()


def test_deploy_refuses_without_coordinator_authorization(monkeypatch):
    monkeypatch.delenv(deploy_mod.AUTH_ENV_VAR, raising=False)
    monkeypatch.setattr(deploy_mod, "_client", _no_aws_client)
    rc = deploy_mod.main(["deploy", "--acknowledge-costs", ROLE, ROLE_VALUE])
    assert rc == 2


def test_deploy_refuses_without_cost_acknowledgement(monkeypatch):
    monkeypatch.setenv(deploy_mod.AUTH_ENV_VAR, "1")
    monkeypatch.setattr(deploy_mod, "_client", _no_aws_client)
    rc = deploy_mod.main(["deploy", ROLE, ROLE_VALUE])
    assert rc == 2


def test_deploy_refuses_without_role(monkeypatch):
    monkeypatch.setenv(deploy_mod.AUTH_ENV_VAR, "1")
    monkeypatch.delenv("SAGEMAKER_ROLE_ARN", raising=False)
    monkeypatch.setattr(deploy_mod, "_client", _no_aws_client)
    rc = deploy_mod.main(["deploy", "--acknowledge-costs"])
    assert rc == 2


def test_dry_run_still_requires_authorization(monkeypatch):
    monkeypatch.delenv(deploy_mod.AUTH_ENV_VAR, raising=False)
    monkeypatch.setattr(deploy_mod, "_client", _no_aws_client)
    rc = deploy_mod.main(
        ["deploy", "--dry-run", "--acknowledge-costs", ROLE, ROLE_VALUE]
    )
    assert rc == 2


def test_delete_requires_authorization(monkeypatch):
    monkeypatch.delenv(deploy_mod.AUTH_ENV_VAR, raising=False)
    monkeypatch.setattr(deploy_mod, "_client", _no_aws_client)
    rc = deploy_mod.main(["delete"])
    assert rc == 2


def test_status_does_not_require_authorization(monkeypatch):
    monkeypatch.delenv(deploy_mod.AUTH_ENV_VAR, raising=False)
    seen = {}

    class FakeClient:
        def describe_endpoint(self, EndpointName):
            seen["endpoint"] = EndpointName
            return {"EndpointStatus": "InService", "CreationTime": "now", "RoleArn": "r"}

    monkeypatch.setattr(deploy_mod, "_client", lambda region: FakeClient())
    rc = deploy_mod.main(["status"])
    assert rc == 0
    assert seen["endpoint"] == "planproof-gemma4-e4b"


def test_image_uri_pinned_to_lmi_with_vllm_0_31():
    uri = deploy_mod.image_uri("eu-west-1")
    assert uri.startswith("763104351884.dkr.ecr.eu-west-1.amazonaws.com/djl-inference:")
    assert "lmi30.0.0" in uri
    assert deploy_mod.MODEL_ID == "google/gemma-4-E4B-it"
    assert deploy_mod.INSTANCE_TYPE == "ml.g5.2xlarge"
    assert deploy_mod.ESTIMATED_USD_PER_HOUR == 1.52


def test_container_env_sizes_model_to_single_a10g():
    env = deploy_mod.CONTAINER_ENV
    assert env["HF_MODEL_ID"] == "google/gemma-4-E4B-it"
    assert env["OPTION_TENSOR_PARALLEL_DEGREE"] == "1"
    assert env["OPTION_DTYPE"] == "bf16"
    assert int(env["OPTION_MAX_MODEL_LEN"]) <= 32768
    assert 0 < float(env["OPTION_GPU_MEMORY_UTILIZATION"]) <= 1.0


def test_require_authorization_enforces_both_gates(monkeypatch):
    monkeypatch.delenv(deploy_mod.AUTH_ENV_VAR, raising=False)

    class Args:
        acknowledge_costs = True

    with pytest.raises(deploy_mod.AuthorizationError, match=deploy_mod.AUTH_ENV_VAR):
        deploy_mod.require_authorization(Args())

    monkeypatch.setenv(deploy_mod.AUTH_ENV_VAR, "1")

    class NoAck(Args):
        acknowledge_costs = False

    with pytest.raises(deploy_mod.AuthorizationError, match="--acknowledge-costs"):
        deploy_mod.require_authorization(NoAck())
