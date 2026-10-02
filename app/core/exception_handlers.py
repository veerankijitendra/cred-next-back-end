import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("Application error: %s | path:%s", exc.message, request.url.path)

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
    logger.warning(
        "Validation error | path=%s | errors=%s",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "message": "Request validation failed",
            "error_code": "VALIDATION_ERROR",
            "details": exc.errors(),
        },
    )


async def sqlalchemy_exception_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception(
        "Unexpected database error | path=%s",
        request.url.path,
    )

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
    logger.exception(
        "Unhandled application error | path=%s",
        request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "error_code": "INTERNAL_SERVER_ERROR",
        },
    )
