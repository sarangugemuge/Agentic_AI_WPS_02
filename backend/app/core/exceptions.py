"""
Custom exceptions and error responses for SkillSync.
"""
from typing import Any, Optional


class SkillSyncException(Exception):
    """Base exception for all application errors."""
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class NotFoundError(SkillSyncException):
    """Resource not found in database."""
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' was not found.",
            status_code=404,
            error_code="NOT_FOUND",
        )


class EntityConflictError(SkillSyncException):
    """Resource already exists or conflicts."""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=409,
            error_code="CONFLICT",
        )


class ServiceUnavailableError(SkillSyncException):
    """External dependency (GitHub API, Gemini AI) is unreachable or timed out."""
    def __init__(self, service_name: str, message: Optional[str] = None):
        msg = message or f"External service '{service_name}' is currently unavailable or timed out."
        super().__init__(
            message=msg,
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
        )


class BusinessValidationError(SkillSyncException):
    """Validation failure in business rules."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="UNPROCESSABLE_ENTITY",
            details=details,
        )
