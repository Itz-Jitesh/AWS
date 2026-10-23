class PlanProofAIError(Exception):
    code = "ai_error"


class LLMUnavailableError(PlanProofAIError):
    code = "llm_unavailable"


class ModelNotConfiguredError(LLMUnavailableError):
    code = "model_not_configured"


class LLMResponseError(PlanProofAIError):
    code = "llm_response_invalid"


class LLMAuthError(LLMUnavailableError):
    code = "llm_auth_error"


class LLMThrottledError(LLMUnavailableError):
    code = "llm_throttled"


class LLMEndpointError(LLMUnavailableError):
    code = "llm_endpoint_error"


class LLMTimeoutError(LLMUnavailableError):
    code = "llm_timeout"


class WorkerError(PlanProofAIError):
    code = "worker_error"


class WorkerUnavailableError(WorkerError):
    code = "worker_unavailable"


class AuditError(PlanProofAIError):
    code = "audit_error"


class PatchValidationError(PlanProofAIError):
    code = "patch_invalid"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class MalformedDiffError(PatchValidationError):
    code = "malformed_diff"


class PathEscapeError(PatchValidationError):
    code = "path_escape"


class DisallowedFileError(PatchValidationError):
    code = "disallowed_file"


class FileDeletedError(PatchValidationError):
    code = "file_deleted"


class DigestMismatchError(PatchValidationError):
    code = "digest_mismatch"


class PatchTooLargeError(PatchValidationError):
    code = "patch_too_large"


class TooManyFilesError(PatchValidationError):
    code = "too_many_files"


class DestructiveChangeError(PatchValidationError):
    code = "destructive_change"


class ContextMismatchError(PatchValidationError):
    code = "context_mismatch"


class BaseMismatchError(PatchValidationError):
    code = "base_mismatch"
