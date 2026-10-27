from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import admin_leads, auth, dashboard, health, leads
from app.core.exception_handlers import (
    app_exception_handler,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import request_id_context, setup_logging
from app.core.rate_limit import enforce_auth_rate_limit

setup_logging()
app = FastAPI(title="CredNext API", version="1.0.0.0")

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def auth_rate_limit_middleware(request: Request, call_next):
    request_id = uuid4().hex
    context_token = request_id_context.set(request_id)
    try:
        response = await enforce_auth_rate_limit(request)
        if response is None:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_context.reset(context_token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.trusted_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(admin_leads.router, prefix="/api/v1")
