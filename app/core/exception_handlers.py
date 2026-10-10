import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("Application error code=%s | path=%s", exc.error_code, request.url.path)

    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    if exc.error_code == "CONFLICT":
        http_status = status.HTTP_409_CONFLICT

    if exc.error_code == "UNAUTHORIZED":
        http_status = status.HTTP_401_UNAUTHORIZED

    if exc.error_code == "FORBIDDEN":
        http_status = status.HTTP_403_FORBIDDEN

    if exc.error_code == "TOO_MANY_REQUESTS":
        http_status = status.HTTP_429_TOO_MANY_REQUESTS

    return JSONResponse(
        status_code=http_status,
        content={
            "success": False,
            "message": exc.message,
            "error_code": exc.error_code,
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    sanitized_details = [
        {"loc": error.get("loc", ()), "msg": error.get("msg", "Invalid value"), "type": error.get("type", "value_error")}
        for error in exc.errors()
    ]
    logger.warning("Validation error | path=%s | fields=%s", request.url.path, [item["loc"] for item in sanitized_details])

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "message": "Request validation failed",
            "error_code": "VALIDATION_ERROR",
            "details": sanitized_details,
        },
    )


async def sqlalchemy_exception_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.error("Unexpected database error | path=%s | exception_type=%s", request.url.path, type(exc).__name__)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "A database error occurred",
            "error_code": "DATABASE_ERROR",
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error("Unhandled application error | path=%s | exception_type=%s", request.url.path, type(exc).__name__)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "error_code": "INTERNAL_SERVER_ERROR",
        },
    )
