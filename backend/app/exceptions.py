"""
SWARMFORGE Exceptions.
"""


class SwarmforgeError(Exception):
    """Base exception for SWARMFORGE engine and API."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFound(SwarmforgeError):
    """Raised when a requested resource (e.g. agent or task) does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class Conflict(SwarmforgeError):
    """Raised when an operation conflicts with current state (e.g. already dead, not running, duplicate)."""

    def __init__(self, message: str = "Conflict with current state") -> None:
        super().__init__(message, status_code=409)


class ValidationError(SwarmforgeError):
    """Raised when input validation fails (e.g. cycle detected, missing dependency)."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, status_code=422)
