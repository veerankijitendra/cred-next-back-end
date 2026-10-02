class AppException(Exception):
    """Base application exception."""

    def __init__(self, *, message: str, error_code: str = "APPLICATION_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class ConflictError(AppException):
    """Raised when a resource already exists."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="CONFLICT",
        )


class UnauthorizedError(AppException):
    """Raised when authentication fails"""

    def __init__(
        self,
        *,
        message: str = "Authentication failed.",
    ) -> None:
        super().__init__(message=message, error_code="UNAUTHORIZED")


class ForbiddenError(AppException):
    """Raised when the authenticated user lacks permission."""

    def __init__(
        self,
        *,
        message: str = "You do not have permission to perform this action.",
    ) -> None:
        super().__init__(message=message, error_code="FORBIDDEN")


class DatabaseError(AppException):
    """Raised when an unexpected database error occurs."""

    def __init__(self, *, message: str) -> None:
        super().__init__(message=message, error_code="DATABASE_ERROR")


class TooManyRequestsError(AppException):
    def __init__(
        self,
        message: str = "Too many requests",
    ):
        super().__init__(
            message=message,
            error_code="TOO_MANY_REQUESTS",
        )
