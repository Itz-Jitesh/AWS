"""Exception types for the PlanProof audit library."""


class AuditError(Exception):
    """Base class for every error raised by the audit library."""


class ContractValidationError(AuditError):
    """A payload did not satisfy its shared contracts/ JSON Schema."""


class NormalizationError(AuditError):
    """A raw scanner record could not be normalized without fabricating data."""


class InvalidPlanError(AuditError):
    """Terraform plan JSON is absent or structurally invalid."""
