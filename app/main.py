from fastapi import FastAPI

from app.api.v1 import health

app = FastAPI(title="CredNext API", version="1.0.0.0")

app.include_router(health.router, prefix="/api/v1")
