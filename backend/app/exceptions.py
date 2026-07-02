"""Domain exceptions raised by the service layer.

Mapped to HTTP responses in main.py; also caught by the agent tool executor so the
model receives structured errors instead of stack traces.
"""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404


class PermissionDeniedError(DomainError):
    status_code = 403


class ValidationFailedError(DomainError):
    status_code = 422


class ConflictError(DomainError):
    status_code = 409
