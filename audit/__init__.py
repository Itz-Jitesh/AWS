"""PlanProof deterministic audit and plan-analysis library (Agent D)."""

from .intent import check_intent
from .normalize import normalize
from .operational import operational_finding
from .plan import classify_plan, loads_plan, plan_digest, verify_digest
from .regression import RegressionResult, compare
from .checkov import run_checkov
from .opa import run_opa

__all__ = [
    "RegressionResult",
    "check_intent",
    "classify_plan",
    "compare",
    "loads_plan",
    "normalize",
    "operational_finding",
    "plan_digest",
    "run_checkov",
    "run_opa",
    "verify_digest",
]
