"""Create, inspect, or delete the PlanProof Gemma 4 SageMaker endpoint.

This script CREATES PAID AWS RESOURCES. It refuses to do anything beyond
`status`/`dry-run` unless BOTH of the following are true:

  1. environment variable PLANPROOF_DEPLOY_AUTHORIZED=1  (set by the
     PlanProof coordinator after approving the cost estimate), and
  2. `--acknowledge-costs` is passed on the command line.

Nothing in tests executes this script (see tests/test_deploy_guard.py which
only verifies the refusal path).

Estimated on-demand cost (us-east-1, Oct 2026, assume no RI/Spot):
  ml.g5.2xlarge SageMaker  ~ $1.52 / hour  (EC2 g5.2xlarge is $1.212/h;
                                            SageMaker adds its platform premium)
  EBS for endpoint storage ~ $0.12 / GB-month (default volume applies)
  S3 model upload          ~ $0 (the LMI container downloads
                            google/gemma-4-E4B-it from Hugging Face at startup;
                            the repo is public / not gated)

Typical integration session (deploy + verify + delete, ~2 h): ~ $3.04.
An endpoint left running for a month: ~ $1,110 (730 h * $1.52).

Usage:
  python deploy/deploy_endpoint.py deploy --region us-east-1 \
      --endpoint-name planproof-gemma4-e4b --acknowledge-costs
  python deploy/deploy_endpoint.py status --region us-east-1 \
      --endpoint-name planproof-gemma4-e4b
  python deploy/deploy_endpoint.py delete --region us-east-1 \
      --endpoint-name planproof-gemma4-e4b --acknowledge-costs
"""

from __future__ import annotations

import argparse
import os
import sys
import time

LMI_IMAGE = (
    "763104351884.dkr.ecr.{region}.amazonaws.com/"
    "djl-inference:0.38.0-lmi30.0.0-cu130"
)
MODEL_ID = "google/gemma-4-E4B-it"
INSTANCE_TYPE = "ml.g5.2xlarge"
INITIAL_INSTANCE_COUNT = 1
ESTIMATED_USD_PER_HOUR = 1.52
AUTH_ENV_VAR = "PLANPROOF_DEPLOY_AUTHORIZED"

# Environment handed to the LMI container. OPTION_MAX_MODEL_LEN and dtype are
# sized for the single 24 GB A10G on ml.g5.2xlarge (BF16 weights ~17.9 GB per
# the Gemma 4 model overview). Verify against LMI 30 release notes before use.
CONTAINER_ENV = {
    "HF_MODEL_ID": MODEL_ID,
    "OPTION_DTYPE": "bf16",
    "OPTION_MAX_MODEL_LEN": "16384",
    "OPTION_TENSOR_PARALLEL_DEGREE": "1",
    "OPTION_GPU_MEMORY_UTILIZATION": "0.90",
    "OPTION_ENABLE_AUTO_TOOL_CHOICE": "false",
}


class AuthorizationError(RuntimeError):
    pass


def require_authorization(args: argparse.Namespace) -> None:
    if os.environ.get(AUTH_ENV_VAR) != "1":
        raise AuthorizationError(
            f"refusing: set {AUTH_ENV_VAR}=1 only after the PlanProof "
            "coordinator approves the cost estimate in "
            "SAGEMAKER_DEPLOYMENT_PLAN.md"
        )
    if not getattr(args, "acknowledge_costs", False):
        raise AuthorizationError(
            "refusing: pass --acknowledge-costs to confirm you have reviewed "
            f"the estimated ${ESTIMATED_USD_PER_HOUR}/hour charge for "
            f"{INSTANCE_TYPE}"
        )


def _client(region: str):
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "boto3 is required for AWS calls: pip install -e 'ai/[aws]'"
        ) from exc
    return boto3.client("sagemaker", region_name=region)


def image_uri(region: str) -> str:
    return LMI_IMAGE.format(region=region)


def deploy(args: argparse.Namespace) -> int:
    require_authorization(args)
    client = _client(args.region)
    print(f"image        : {image_uri(args.region)}")
    print(f"model        : {MODEL_ID}")
    print(f"instance     : {INSTANCE_TYPE} x{INITIAL_INSTANCE_COUNT}")
    print(f"est. cost    : ~${ESTIMATED_USD_PER_HOUR}/hour while running")
    if args.dry_run:
        print("dry-run      : no resources created")
        return 0

    model = client.create_model(
        ModelName=args.model_name,
        ExecutionRoleArn=args.role_arn,
        PrimaryContainer={
            "Image": image_uri(args.region),
            "Environment": CONTAINER_ENV,
        },
    )
    print(f"model created: {model['ModelArn']}")

    config_kwargs: dict = {
        "EndpointConfigName": args.config_name,
        "ProductionVariants": [
            {
                "VariantName": "AllTraffic",
                "ModelName": args.model_name,
                "InstanceType": INSTANCE_TYPE,
                "InitialInstanceCount": INITIAL_INSTANCE_COUNT,
                "InitialVariantWeight": 1.0,
            }
        ],
    }
    if args.artifact_bucket:
        config_kwargs["DataCaptureConfig"] = {
            "EnableCapture": False,
            "InitialSamplingPercentage": 0,
            "DestinationS3Uri": f"s3://{args.artifact_bucket}/planproof-datacapture",
        }
    config_kwargs["CreationPendingTimeout"] = 3600
    config = client.create_endpoint_config(**config_kwargs)
    print(f"config created: {config['EndpointConfigArn']}")

    endpoint = client.create_endpoint(
        EndpointName=args.endpoint_name, EndpointConfigName=args.config_name
    )
    print(f"endpoint creating: {endpoint['EndpointArn']}")
    print(
        "model download from Hugging Face happens at container startup; "
        "first InService can take 5-20 minutes. Watch with: "
        f"`{os.path.basename(sys.argv[0])} status --endpoint-name "
        f"{args.endpoint_name} --region {args.region}`"
    )
    return 0


def status(args: argparse.Namespace) -> int:
    client = _client(args.region)
    try:
        desc = client.describe_endpoint(EndpointName=args.endpoint_name)
    except Exception as exc:
        print(f"endpoint not found or not readable: {exc}", file=sys.stderr)
        return 1
    print(f"status  : {desc.get('EndpointStatus')}")
    print(f"created : {desc.get('CreationTime')}")
    print(f"role    : {desc.get('RoleArn', 'n/a')}")
    failure = desc.get("FailureReason")
    if failure:
        print(f"failure : {failure}")
    return 0 if desc.get("EndpointStatus") in {"InService", "Creating"} else 1


def delete(args: argparse.Namespace) -> int:
    require_authorization(args)
    client = _client(args.region)
    if args.dry_run:
        print(f"dry-run: would delete endpoint {args.endpoint_name}")
        return 0
    try:
        client.delete_endpoint(EndpointName=args.endpoint_name)
        print(f"endpoint deleting: {args.endpoint_name}")
    except Exception as exc:
        print(f"endpoint delete skipped: {exc}", file=sys.stderr)
    for name_kind, name in (
        ("endpoint config", args.config_name),
        ("model", args.model_name),
    ):
        try:
            if name_kind == "endpoint config":
                client.delete_endpoint_config(EndpointConfigName=name)
            else:
                client.delete_model(ModelName=name)
            print(f"{name_kind} deleted: {name}")
        except Exception as exc:
            print(f"{name_kind} delete skipped: {exc}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--endpoint-name", default="planproof-gemma4-e4b")
    common.add_argument("--model-name", default="planproof-gemma4-e4b")
    common.add_argument("--config-name", default="planproof-gemma4-e4b")
    common.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    common.add_argument("--role-arn", default=os.environ.get("SAGEMAKER_ROLE_ARN", ""))
    common.add_argument("--artifact-bucket", default="")
    common.add_argument("--acknowledge-costs", action="store_true")
    common.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deploy", parents=[common], help="create model + endpoint (paid)")
    sub.add_parser("status", parents=[common], help="describe endpoint (free)")
    sub.add_parser("delete", parents=[common], help="tear down (stops billing)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "deploy":
        if not args.role_arn:
            print("refusing: --role-arn or SAGEMAKER_ROLE_ARN is required", file=sys.stderr)
            return 2
        try:
            return deploy(args)
        except AuthorizationError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "status":
        return status(args)
    try:
        return delete(args)
    except AuthorizationError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
