from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base error with a stable machine-readable ``code``."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} '{identifier}' not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BadRequestError(AppError):
    def __init__(self, message: str, code: str = "BAD_REQUEST") -> None:
        super().__init__(message=message, code=code, status_code=400)


class UnauthorizedError(AppError):
    def __init__(
        self, message: str = "Authentication required", code: str = "UNAUTHORIZED"
    ) -> None:
        super().__init__(message=message, code=code, status_code=401)


class ConflictError(AppError):
    def __init__(self, message: str, code: str = "CONFLICT") -> None:
        super().__init__(message=message, code=code, status_code=409)


class AlreadyExistsError(AppError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code="ALREADY_EXISTS",
            message=f"{resource} '{identifier}' already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(
            code="AUTH_FAILED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class InvalidTransitionError(AppError):
    """Raised when a state-machine transition is not allowed."""

    def __init__(self, entity: str, current: str, target: str):
        super().__init__(
            code="INVALID_TRANSITION",
            message=f"{entity} cannot transition from '{current}' to '{target}'",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
